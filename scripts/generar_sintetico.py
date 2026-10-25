"""Genera datos SINTÉTICOS con la estructura de la base del HUN (OMOP) en un
PostgreSQL LOCAL de pruebas. Ningún dato es real: todo sale de distribuciones
inventadas que imitan los patrones observados (en palabras) en la exploración.

Sirve para:
  - probar consultas y código sin conectarse a la base del HUN,
  - compartir ejemplos con IA o en el repo sin riesgo,
  - tests reproducibles.

Uso (PostgreSQL local, NUNCA el del HUN; la URL debe traer host y base explícitos):
  python scripts/generar_sintetico.py --url postgresql://usuario@localhost:5432/omop_sintetico
  python scripts/generar_sintetico.py --url ... --pacientes 5000 --semilla 7

Patrones que imita:
  - 9203 "Emergency Room Visit": marca de llegada, dura 0 o pocos minutos,
    solapada con el inicio de la atención.
  - 3045729 "Treatment urgency": estancia en urgencias (típico 1-4 h, cola larga),
    a veces partida en varios segmentos seguidos; una parte dura 0.
  - 9201 "Inpatient Visit": hospitalización (típico 1-7 días), casi siempre
    seguida al fin de urgencias; a veces con hueco de horas o días.
  - 581479 "Ambulatory Rehabilitation Visit": eventos puntuales de duración 0.
  - visit_occurrence con inicio = fin y que agrupa episodios separados por días.
  - Llegadas con perfil horario, algo más de demanda los lunes, estacionalidad anual
    suave y una tendencia leve (todo inventado), para probar las series de tiempo.
  - condition_occurrence, procedure_occurrence (solo fecha) y measurement con unos
    pocos conceptos inventados, para que la guía de familiarización corra completa.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import numpy as np
import psycopg2
from psycopg2.extras import execute_values

ER, TU, IP, AMB = 9203, 3045729, 9201, 581479
CONCEPTOS = [
    (ER, "Emergency Room Visit", "Visit", "Visit"),
    (TU, "Treatment urgency {Diagnosis}", "Observation", "LOINC"),
    (IP, "Inpatient Visit", "Visit", "Visit"),
    (AMB, "Ambulatory Rehabilitation Visit", "Visit", "Visit"),
    (0, "No matching concept", "Metadata", "None"),
    (8507, "MALE", "Gender", "Gender"),
    (8532, "FEMALE", "Gender", "Gender"),
    (32817, "EHR", "Type Concept", "Type Concept"),
]
# Conceptos clínicos de ejemplo. Son solo para probar: los IDs no tienen por qué coincidir con
# el vocabulario OMOP real y las frecuencias y valores son inventados.
DIAGNOSTICOS = [(4329041, "Pain", 0.30), (200219, "Abdominal pain", 0.25), (437663, "Fever", 0.20),
                (201826, "Type 2 diabetes mellitus", 0.10), (320128, "Essential hypertension", 0.15)]
PROCEDIMIENTOS = [(4163872, "Plain chest X-ray", 0.5), (4125350, "Ultrasonography of abdomen", 0.3),
                  (4058336, "Electrocardiogram", 0.2)]
LABORATORIOS = [(3000963, "Hemoglobin [Mass/volume] in Blood", 12.0, 2.0),
                (3016723, "Creatinine [Mass/volume] in Serum or Plasma", 1.0, 0.4),
                (3019550, "Sodium [Moles/volume] in Serum or Plasma", 139.0, 4.0)]
CONCEPTOS += [(c, n, "Condition", "SNOMED") for c, n, _ in DIAGNOSTICOS]
CONCEPTOS += [(c, n, "Procedure", "SNOMED") for c, n, _ in PROCEDIMIENTOS]
CONCEPTOS += [(c, n, "Measurement", "LOINC") for c, n, _, _ in LABORATORIOS]

DDL = """
DROP SCHEMA IF EXISTS uninorte_omop CASCADE;
CREATE SCHEMA uninorte_omop;
SET search_path = uninorte_omop;
CREATE TABLE _es_sintetico (creado timestamp DEFAULT now());   -- marca: este esquema es inventado
INSERT INTO _es_sintetico DEFAULT VALUES;
CREATE TABLE concept (concept_id int, concept_name text, domain_id text, vocabulary_id text);
CREATE TABLE person (person_id int, gender_concept_id int, year_of_birth int,
                     race_concept_id int, ethnicity_concept_id int);
CREATE TABLE visit_occurrence (visit_occurrence_id int, person_id int, visit_concept_id int,
                     visit_start_datetime timestamp, visit_end_datetime timestamp, provider_id int);
CREATE TABLE visit_detail (visit_detail_id int, visit_occurrence_id int, visit_detail_concept_id int,
                     visit_detail_start_datetime timestamp, visit_detail_end_datetime timestamp,
                     provider_id int);
CREATE TABLE condition_occurrence (condition_occurrence_id int, person_id int, visit_occurrence_id int,
                     condition_concept_id int, condition_start_datetime timestamp,
                     condition_type_concept_id int);
CREATE TABLE procedure_occurrence (procedure_occurrence_id int, person_id int, visit_occurrence_id int,
                     procedure_concept_id int, procedure_date date);
CREATE TABLE measurement (measurement_id int, person_id int, visit_occurrence_id int,
                     measurement_concept_id int, measurement_datetime timestamp, value_as_number numeric,
                     measurement_source_value_extended text);
"""

# --- Protecciones: este script BORRA y recrea el esquema uninorte_omop. -------------------
# Tres capas independientes para que nunca pueda tocar la base del HUN:
#   1. La URL debe traer host explícito local y no puede redirigir con ?host= / ?service=.
#   2. Se borran del entorno PGHOST & cía. y, ya conectado, se confirma que el servidor es local.
#   3. Solo se borra un esquema uninorte_omop que tenga la marca _es_sintetico (creada por este
#      script). Si existe uno SIN marca, podría ser real: se aborta.
_HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}
_VARS_PELIGROSAS = ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGDATABASE")
_PARAMS_PROHIBIDOS = {"host", "hostaddr", "service", "dbname", "options"}


def _abortar(motivo: str) -> None:
    raise SystemExit(f"ABORTADO por seguridad: {motivo}\n"
                     "Este script solo escribe en un PostgreSQL LOCAL de pruebas, nunca en la base del HUN.")


def _validar_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in {"postgresql", "postgres"}:
        _abortar("la URL debe empezar por postgresql://")
    if "," in u.netloc:
        _abortar("la URL no puede traer varios hosts")
    if not u.hostname:
        _abortar("la URL debe traer el host explícito (p. ej. postgresql://yo@localhost:5432/omop_sintetico)")
    if u.hostname.lower() not in _HOSTS_LOCALES:
        _abortar(f"el host '{u.hostname}' no es local")
    if not u.path.strip("/"):
        _abortar("la URL debe traer el nombre de la base (…/omop_sintetico)")
    prohibidos = _PARAMS_PROHIBIDOS & {k.lower() for k in parse_qs(u.query)}
    if prohibidos:
        _abortar(f"la URL no puede traer los parámetros {sorted(prohibidos)}")


def _verificar_servidor_local(cur) -> None:
    cur.execute("SELECT host(inet_server_addr())")
    addr = cur.fetchone()[0]                 # None = socket local de Unix
    if addr is not None:
        ip = ipaddress.ip_address(addr)
        if ip.version == 6 and ip.ipv4_mapped:           # ::ffff:127.0.0.1 -> 127.0.0.1
            ip = ip.ipv4_mapped
        if not ip.is_loopback:
            _abortar(f"el servidor conectado no es local ({addr})")


def _verificar_esquema_es_sintetico(cur) -> None:
    cur.execute("SELECT to_regnamespace('uninorte_omop') IS NOT NULL, "
                "to_regclass('uninorte_omop._es_sintetico') IS NOT NULL")
    existe, marcado = cur.fetchone()
    if existe and not marcado:
        _abortar("ya existe un esquema uninorte_omop SIN la marca de sintético; podría ser real")


# Perfil de llegadas por hora (inventado): pico de mañana y de tarde-noche
_PERFIL_HORA = np.array([2, 1.5, 1, 1, 1, 1.5, 3, 5, 7, 8, 8, 7,
                         6, 6, 6, 6, 6.5, 7, 7.5, 7, 6, 5, 4, 3], dtype=float)
_PERFIL_HORA /= _PERFIL_HORA.sum()


def _pesos_dias(inicio: datetime, dias: int) -> np.ndarray:
    """Probabilidad de cada día del rango: estacionalidad anual suave (pico a mitad de año) y
    tendencia leve al alza. Inventado, solo para que las series tengan algo que descomponer."""
    d = np.arange(dias)
    doy = np.array([(inicio + timedelta(days=int(i))).timetuple().tm_yday for i in d])
    w = (1 + 0.15 * np.sin(2 * np.pi * (doy - 80) / 365.25)) * (1 + 0.10 * d / max(dias, 1))
    return w / w.sum()


def _llegada(rng, inicio: datetime, pesos: np.ndarray) -> datetime:
    dia = inicio + timedelta(days=int(rng.choice(len(pesos), p=pesos)))
    # un poco más de demanda los lunes (estacionalidad semanal inventada)
    if dia.weekday() != 0 and rng.random() < 0.08:
        dia += timedelta(days=(7 - dia.weekday()) % 7)
    hora = int(rng.choice(24, p=_PERFIL_HORA))
    return dia.replace(hour=hora, minute=int(rng.integers(0, 60)))


def generar(n_pacientes: int, semilla: int, inicio: datetime, dias: int):
    rng = np.random.default_rng(semilla)
    pesos = _pesos_dias(inicio, dias)
    personas, visitas, detalles = [], [], []
    vid = did = 0

    def seg(visita, cid, ini, fin):
        nonlocal did
        did += 1
        detalles.append((did, visita, cid, ini, fin, int(rng.integers(1, 200))))

    for pid in range(1, n_pacientes + 1):
        personas.append((pid, int(rng.choice([8507, 8532])), int(rng.integers(1935, 2024)), 0, 0))
        for _ in range(int(rng.poisson(1.3)) + 1):          # visitas (agrupadores) por paciente
            vid += 1
            t0 = _llegada(rng, inicio, pesos)
            tipo = rng.choice(["urg", "amb", "hosp_directa"], p=[0.55, 0.35, 0.10])
            primeros = []

            # eventos ambulatorios puntuales antes (agrupados en la misma visita)
            if tipo == "amb" or rng.random() < 0.3:
                t = t0 - timedelta(days=int(rng.integers(1, 20)))
                for _ in range(int(rng.integers(1, 4))):
                    seg(vid, AMB, t, t)
                    primeros.append((t, AMB))
                    t += timedelta(days=int(rng.integers(1, 10)))

            if tipo == "urg":
                llegada_er = t0
                seg(vid, ER, llegada_er, llegada_er + timedelta(minutes=int(rng.choice([0, 0, 3, 8, 12]))))
                primeros.append((llegada_er, ER))
                dur = 0.0 if rng.random() < 0.25 else float(rng.lognormal(np.log(180), 0.9))
                hosp = rng.random() < 0.18
                if hosp:
                    dur += float(rng.lognormal(np.log(300), 0.8))   # espera de cama dentro de urgencias
                t, restante = llegada_er + timedelta(minutes=int(rng.integers(0, 5))), dur
                for _ in range(int(rng.integers(1, 4))):            # atención partida en segmentos seguidos
                    tramo = restante if restante < 60 else restante * float(rng.uniform(0.3, 1.0))
                    seg(vid, TU, t, t + timedelta(minutes=tramo))
                    t += timedelta(minutes=tramo)
                    restante -= tramo
                    if restante <= 1:
                        break
                if hosp:
                    hueco = 0 if rng.random() < 0.7 else float(rng.choice([rng.uniform(360, 1440),
                                                                            rng.uniform(1440, 4320)]))
                    ti = t + timedelta(minutes=hueco)
                    los = float(rng.lognormal(np.log(3 * 1440), 0.8))
                    corte = ti + timedelta(minutes=los * float(rng.uniform(0.3, 0.7)))
                    seg(vid, IP, ti, corte)
                    seg(vid, IP, corte, ti + timedelta(minutes=los))

            if tipo == "hosp_directa":
                los = float(rng.lognormal(np.log(2 * 1440), 0.7))
                seg(vid, IP, t0, t0 + timedelta(minutes=los))
                primeros.append((t0, IP))

            concepto = {"urg": ER if rng.random() < 0.4 else TU, "amb": AMB, "hosp_directa": IP}[tipo]
            inicio_visita = min(primeros)[0] if primeros and rng.random() < 0.7 else t0
            visitas.append((vid, pid, int(concepto), inicio_visita, inicio_visita, int(rng.integers(1, 200))))

    # algunas visitas sin segmentos ("No matching concept")
    for _ in range(n_pacientes // 20):
        vid += 1
        t = _llegada(rng, inicio, pesos)
        visitas.append((vid, int(rng.integers(1, n_pacientes + 1)), 0, t, t, 1))
    return personas, visitas, detalles


def clinicos(rng, visitas, detalles):
    """Diagnósticos, procedimientos (solo fecha) y laboratorios inventados para las visitas
    que pasan por urgencias u hospitalización."""
    inicio_seg: dict[int, datetime] = {}
    for _, v, cid, ini, _, _ in detalles:
        if cid in (ER, TU, IP) and (v not in inicio_seg or ini < inicio_seg[v]):
            inicio_seg[v] = ini
    persona = {v[0]: v[1] for v in visitas}
    cond, proc, meas = [], [], []
    p_dx = np.array([x[2] for x in DIAGNOSTICOS]); p_dx /= p_dx.sum()
    p_px = np.array([x[2] for x in PROCEDIMIENTOS]); p_px /= p_px.sum()
    for v, t in inicio_seg.items():
        for _ in range(int(rng.integers(1, 3))):
            dx = DIAGNOSTICOS[int(rng.choice(len(DIAGNOSTICOS), p=p_dx))][0]
            cond.append((len(cond) + 1, persona[v], v, dx, t + timedelta(minutes=int(rng.integers(5, 120))), 32817))
        if rng.random() < 0.6:
            px = PROCEDIMIENTOS[int(rng.choice(len(PROCEDIMIENTOS), p=p_px))][0]
            proc.append((len(proc) + 1, persona[v], v, px, (t + timedelta(hours=int(rng.integers(0, 12)))).date()))
        for _ in range(int(rng.poisson(2))):
            c, _, media, de = LABORATORIOS[int(rng.integers(0, len(LABORATORIOS)))]
            valor = None if rng.random() < 0.05 else round(float(rng.normal(media, de)), 2)
            meas.append((len(meas) + 1, persona[v], v, c, t + timedelta(minutes=int(rng.integers(10, 240))),
                         valor, "sintetico"))
    return cond, proc, meas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="PostgreSQL LOCAL, p. ej. postgresql://yo@localhost/omop_sintetico")
    ap.add_argument("--pacientes", type=int, default=3000)
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--dias", type=int, default=730, help="días del rango (por defecto dos años)")
    a = ap.parse_args()

    _validar_url(a.url)
    for var in _VARS_PELIGROSAS:          # que libpq no tome el host/servicio del entorno
        os.environ.pop(var, None)

    personas, visitas, detalles = generar(a.pacientes, a.semilla, datetime(2023, 1, 2), a.dias)
    cond, proc, meas = clinicos(np.random.default_rng(a.semilla + 1), visitas, detalles)
    with psycopg2.connect(a.url) as con, con.cursor() as cur:
        _verificar_servidor_local(cur)
        _verificar_esquema_es_sintetico(cur)
        cur.execute(DDL)
        execute_values(cur, "INSERT INTO concept VALUES %s", CONCEPTOS)
        execute_values(cur, "INSERT INTO person VALUES %s", personas)
        execute_values(cur, "INSERT INTO visit_occurrence VALUES %s", visitas)
        execute_values(cur, "INSERT INTO visit_detail VALUES %s", detalles)
        execute_values(cur, "INSERT INTO condition_occurrence VALUES %s", cond)
        execute_values(cur, "INSERT INTO procedure_occurrence VALUES %s", proc)
        execute_values(cur, "INSERT INTO measurement VALUES %s", meas)
        cur.execute("CREATE INDEX ON visit_detail (visit_occurrence_id); "
                    "CREATE INDEX ON visit_occurrence (visit_occurrence_id); ANALYZE;")
    print(f"Sintético listo en el esquema uninorte_omop: {len(personas)} personas, "
          f"{len(visitas)} visitas, {len(detalles)} segmentos, {len(cond)} diagnósticos, "
          f"{len(proc)} procedimientos y {len(meas)} laboratorios (todo inventado).")


if __name__ == "__main__":
    main()

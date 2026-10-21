# Notebooks

Cargan extractos desde `DATA_DIR` con `hun.extract.load("<nombre>")`. Se commitean **sin outputs**: las celdas ejecutadas guardan tablas y gráficas con datos dentro del `.ipynb`.

Para limpiar automáticamente, una vez por clon: `nbstripout --install`
O a mano antes de commitear: `jupyter nbconvert --clear-output --inplace notebooks/*.ipynb`

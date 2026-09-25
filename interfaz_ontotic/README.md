# Interfaz OntoTIC de 43 actores

**Autor: PhD. Carlos Andrés Salazar**

Código de la interfaz local para caracterización de capacidades y exploración de posibles colaboraciones. El índice de complementariedad expresa hipótesis analíticas, no alianzas observadas.

## Instalación

Para utilizar la aplicación con los 43 actores y 9.521 registros, descargue el paquete completo de la interfaz y copie en esta carpeta `data/ontotic.sqlite`, `static/network.gexf` y `static/network.png`. Los archivos de trabajo de la carpeta `sources/` del paquete permiten reconstruir la base ejecutando `py seed.py`; ejecutar ese comando reemplaza la base existente.

En Windows: `py -m pip install -r requirements.txt`, luego `py app.py` y abra `http://127.0.0.1:8765`.

El código se publica separado del corpus, la matriz y la base SQLite para evitar distribuir materiales de investigación en este repositorio. La interfaz se ejecuta localmente y no incorpora autenticación para publicación en Internet.

import sqlite3

conn = sqlite3.connect('database.db')
c = conn.cursor()

try:
    c.execute("ALTER TABLE eventos ADD COLUMN descripcion TEXT")
except sqlite3.OperationalError:
    # La columna ya existe
    pass

try:
    c.execute("ALTER TABLE eventos ADD COLUMN materiales TEXT")
except sqlite3.OperationalError:
    # La columna ya existe
    pass

conn.commit()
conn.close()

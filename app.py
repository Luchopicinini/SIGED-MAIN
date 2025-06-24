import sqlite3
from flask import Flask, render_template, request, redirect, session, url_for
import os
from functools import wraps
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Clave secreta para sesiones

# ==================== CONFIGURACIÓN GOOGLE SHEETS ====================
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

SERVICE_ACCOUNT_FILE = 'credentials.json'

try:
    # Autenticación con Google Sheets
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open("inventario").sheet1

    # Crear encabezados si no existen
    if sheet.row_count == 0 or not sheet.row_values(1):
        sheet.append_row(['Nombre', 'Tipo Usuario', 'Prioridad', 'Fecha', 'Hora', 'Lugar', 'Materiales', 'Descripción', 'Estado'])
except Exception as e:
    print("[ERROR - Google Sheets]", e)
    sheet = None


# ==================== DECORADORES Y BASE DE DATOS ====================

# Decorador para proteger rutas solo para admin

def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('login_unico'))
        return f(*args, **kwargs)
    return decorated

# Crear tabla eventos si no existe

def crear_base():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                tipo_usuario TEXT,
                prioridad INTEGER,
                fecha TEXT,
                hora TEXT,
                lugar TEXT,
                materiales TEXT,
                descripcion TEXT,
                estado TEXT
            )
        ''')
        conn.commit()

# Intentar agregar columnas si no existen

def actualizar_tabla():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        try:
            c.execute("ALTER TABLE eventos ADD COLUMN descripcion TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE eventos ADD COLUMN materiales TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()

# Obtener solicitudes desde base de datos

def obtener_solicitudes():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, nombre, tipo_usuario, prioridad, fecha, hora, lugar, estado, descripcion, materiales
            FROM eventos ORDER BY fecha DESC
        """)
        return c.fetchall()


# ==================== RUTAS DE LA APLICACIÓN ====================

@app.route('/')
def index():
    return redirect(url_for('login_unico'))

# Ruta de login
@app.route('/login', methods=['GET', 'POST'])
def login_unico():
    if request.method == 'POST':
        correo = request.form['correo']
        password = request.form['password']
        dominio = correo.split('@')[-1]

        # Validación simple de contraseña
        if password != '1111':
            return render_template('login_unico.html', error="Contraseña incorrecta")

        if correo == 'admin@duocuc.cl':
            session['admin'] = True
            session['usuario'] = correo
            session['tipo_usuario'] = 'Admin'
            return redirect(url_for('jefe_panel'))

        session['usuario'] = correo

        jefes = ['jefe.carrera@duocuc.cl']
        if correo in jefes:
            tipo_usuario = 'Jefe de Carrera'
        elif dominio == 'duocuc.cl':
            tipo_usuario = 'Profesor'
        else:
            tipo_usuario = 'Cliente Externo'

        session['tipo_usuario'] = tipo_usuario
        return redirect(url_for('inicio_cliente'))

    return render_template('login_unico.html')

# Vista inicial del cliente
@app.route('/inicio_cliente')
def inicio_cliente():
    return render_template('inicio_cliente.html')

# Panel del jefe de carrera
@app.route('/jefe_panel')
@login_requerido
def jefe_panel():
    solicitudes = obtener_solicitudes()
    return render_template('jefe_panel.html', solicitudes=solicitudes)

# Cambiar estado desde panel admin
@app.route('/admin/cambiar_estado/<int:id>', methods=['POST'])
@login_requerido
def cambiar_estado(id):
    nuevo_estado = request.form['nuevo_estado']
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE eventos SET estado = ? WHERE id = ?", (nuevo_estado, id))
        conn.commit()
    return redirect(url_for('jefe_panel'))

# Página para enviar solicitud
@app.route('/enviar_solicitud')
def enviar_solicitud():
    return render_template('enviar_solicitud.html')

@app.route('/admin/enviar_solicitud')
@login_requerido
def enviar_solicitud_admin():
    return render_template('enviar_solicitud_admin.html')

# Logout de administrador
@app.route('/admin/logout')
@login_requerido
def logout():
    session.clear()
    return redirect(url_for('login_unico'))

# Logout para usuario común
@app.route('/logout_usuario')
def logout_usuario():
    session.pop('usuario', None)
    session.pop('tipo_usuario', None)
    return redirect(url_for('login_unico'))

# Acceso directo a formulario por tipo
@app.route('/formulario_directo/<tipo_usuario>')
def formulario_directo(tipo_usuario):
    return render_template('solicitar_evento.html', tipo_usuario=tipo_usuario)

# Formulario para solicitar evento
@app.route('/solicitar_evento')
def solicitar_evento():
    tipo_usuario = session.get('tipo_usuario', 'Alumno')
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("SELECT nombre, fecha FROM eventos WHERE estado IN ('Pendiente', 'Aprobado')")
        eventos = [{'nombre': row[0], 'fecha': row[1]} for row in c.fetchall()]
    return render_template('solicitar_evento.html', tipo_usuario=tipo_usuario, eventos=eventos)

# Vista de solicitudes del usuario
@app.route('/mis_solicitudes')
def mis_solicitudes():
    tipo_usuario = session.get('tipo_usuario')
    if not tipo_usuario:
        return redirect(url_for('login_unico'))

    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, nombre, fecha, hora, lugar, estado, descripcion, materiales
            FROM eventos
            WHERE tipo_usuario = ?
            ORDER BY fecha DESC
        ''', (tipo_usuario,))
        solicitudes = c.fetchall()

    return render_template('mis_solicitudes.html', solicitudes=solicitudes)

# Guardar nueva solicitud
@app.route('/enviar', methods=['POST'])
def enviar():
    nombre = request.form['nombre']
    tipo_usuario = request.form['tipo_usuario']
    fecha = request.form['fecha']
    hora = request.form['hora']
    lugar = request.form['lugar']
    materiales = request.form['materiales']
    descripcion = request.form.get('descripcion', '')

    prioridades = {
        'Alumno': 1,
        'Profesor': 2,
        'Cliente Externo': 2,
        'Jefe de Carrera': 3,
        'Admin': 4
    }
    prioridad = prioridades.get(tipo_usuario, 1)

    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO eventos (nombre, tipo_usuario, prioridad, fecha, hora, lugar, materiales, descripcion, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente')
        ''', (nombre, tipo_usuario, prioridad, fecha, hora, lugar, materiales, descripcion))
        conn.commit()

    # Guardar también en Google Sheets
    if sheet:
        try:
            sheet.append_row([nombre, tipo_usuario, prioridad, fecha, hora, lugar, materiales, descripcion, 'Pendiente'])
            print("✅ Evento enviado a Google Sheets.")
        except Exception as e:
            print("[ERROR al guardar en Google Sheets]", e)

    return redirect(url_for('mis_solicitudes'))

# Historial para admin
@app.route('/historial_eventos')
@login_requerido
def historial_eventos():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, nombre, fecha, estado FROM eventos ORDER BY fecha DESC")
        historial = c.fetchall()
    return render_template('historial_eventos.html', historial=historial)

# Formulario para áreas especiales
@app.route('/formulario_area/<area>', methods=['GET', 'POST'])
@login_requerido
def formulario_area(area):
    if request.method == 'POST':
        nombre = request.form['nombre']
        fecha = request.form['fecha']
        hora = request.form['hora']
        lugar = request.form['lugar']
        materiales = request.form.get('materiales', '')
        descripcion = request.form.get('descripcion', '')
        tipo_usuario = area

        prioridades = {
            'Área de Aseo': 3,
            'Área de Gestión Inmobiliaria': 3,
            'Coordinador de Carrera': 3,
            'Admin': 4
        }
        prioridad = prioridades.get(tipo_usuario, 1)

        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO eventos (nombre, tipo_usuario, prioridad, fecha, hora, lugar, materiales, descripcion, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente')
            ''', (nombre, tipo_usuario, prioridad, fecha, hora, lugar, materiales, descripcion))
            conn.commit()

        return redirect(url_for('jefe_panel'))

    return render_template('enviar_solicitud_area.html', area=area)

# Contactos DUOC
@app.route('/contacto_duoc')
@login_requerido
def contacto_duoc():
    contactos = [
        {"nombre": "Juan Perez", "email": "juan.perez@duocuc.cl"},
        {"nombre": "Maria Lopez", "email": "maria.lopez@duocuc.cl"},
        {"nombre": "Carlos Martínez", "email": "carlos.martinez@duocuc.cl"},
    ]
    return render_template('contacto_duoc.html', contactos=contactos)

# Procesamiento de solicitudes internas
@app.route('/procesar_solicitud', methods=['POST'])
@login_requerido
def procesar_solicitud():
    tipo = request.form.get('tipo_solicitud')
    detalle = request.form.get('detalle')

    nombre = "Solicitud interna"
    tipo_usuario = "Admin"
    prioridad = 3
    fecha = ""
    hora = ""
    lugar = ""
    materiales = detalle
    descripcion = f"Solicitud para {tipo}"

    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO eventos (nombre, tipo_usuario, prioridad, fecha, hora, lugar, materiales, descripcion, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente')
        ''', (nombre, tipo_usuario, prioridad, fecha, hora, lugar, materiales, descripcion))
        conn.commit()

    return redirect(url_for('jefe_panel'))

# Áreas disponibles para el admin
@app.route('/areas_admin')
@login_requerido
def areas_admin():
    areas = ['Auditorio', 'Biblioteca', 'Coliseo', 'Hall 2', 'Sala Multimedia']
    return render_template('areas_admin.html', areas=areas)

@app.route('/limpiar_db')
@login_requerido
def limpiar_db():
    try:
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            c.execute("DELETE FROM eventos")  # Borra todos los registros
            conn.commit()
        return "✅ Base de datos vaciada con éxito."
    except Exception as e:
        return f"❌ Error al vaciar la base de datos: {e}"

@app.route('/admin/eliminar_solicitud/<int:id>', methods=['POST'])
@login_requerido
def eliminar_solicitud(id):
    try:
        with sqlite3.connect('database.db') as conn:
            c = conn.cursor()
            # Obtener datos para identificar la fila en Sheets
            c.execute("SELECT nombre, tipo_usuario, prioridad, fecha, hora, lugar, materiales, descripcion, estado FROM eventos WHERE id = ?", (id,))
            evento = c.fetchone()
            
            # Eliminar de SQLite
            c.execute("DELETE FROM eventos WHERE id = ?", (id,))
            conn.commit()

        # Eliminar de Google Sheets si está configurado
        if sheet and evento:
            try:
                # Obtener todas las filas de la hoja (sin encabezado)
                all_rows = sheet.get_all_values()
                # Buscar la fila que coincide (asumiendo que el encabezado está en la fila 1)
                # Buscamos fila exacta que coincida con todos los datos de evento
                for idx, row in enumerate(all_rows[1:], start=2):  # fila 2 en adelante
                    if row[:9] == list(map(str, evento)):
                        sheet.delete_row(idx)
                        break
            except Exception as e:
                print("[ERROR al eliminar de Google Sheets]", e)

        return redirect(url_for('jefe_panel'))

    except Exception as e:
        return f"Error al eliminar la solicitud: {e}"



# Inicializar app
if __name__ == '__main__':
    crear_base()
    actualizar_tabla()
    app.run(debug=True)

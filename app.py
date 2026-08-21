import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime
import hashlib
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ==========================================
# CONFIGURACIÓN E INICIALIZACIÓN DE BD (SUPABASE)
# ==========================================
st.set_page_config(page_title="AURANZA SAS - ERP/MRP System", layout="wide", page_icon="🧪")

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

# OPTIMIZACIÓN: Conexión persistente mediante cache_resource
@st.cache_resource
def get_connection():
    conn = psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        port=st.secrets["postgres"]["port"],
        database=st.secrets["postgres"]["dbname"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        cursor_factory=psycopg2.extras.DictCursor
    )
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Tabla de Usuarios
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password TEXT NOT NULL,
            rol VARCHAR(50) NOT NULL
        )""")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bodegas (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(100) UNIQUE NOT NULL
        )""")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id SERIAL PRIMARY KEY,
            nombre VARCHAR(150) UNIQUE NOT NULL,
            nit VARCHAR(50),
            contacto TEXT,
            telefono VARCHAR(50),
            email VARCHAR(100)
        )""")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id SERIAL PRIMARY KEY,
            codigo_au VARCHAR(100) UNIQUE NOT NULL,
            codigo_proveedor VARCHAR(100) NOT NULL,
            nombre_au TEXT NOT NULL,
            nombre_proveedor TEXT NOT NULL,
            proveedor TEXT NOT NULL,
            categoria VARCHAR(100) NOT NULL,
            linea VARCHAR(100) NOT NULL,
            bodega_id INTEGER NOT NULL REFERENCES bodegas(id),
            unidad_medida VARCHAR(20) DEFAULT 'KG',
            costo_promedio NUMERIC DEFAULT 0.0,
            ultimo_costo NUMERIC DEFAULT 0.0,
            fecha_ultimo_costo TEXT,
            precio_venta NUMERIC DEFAULT 0.0,
            punto_pedido NUMERIC DEFAULT 0.0,
            nivel_minimo NUMERIC DEFAULT 0.0,
            nivel_maximo NUMERIC DEFAULT 0.0,
            comp_venta NUMERIC DEFAULT 0.0,
            comp_op NUMERIC DEFAULT 0.0,
            comp_requisicion NUMERIC DEFAULT 0.0,
            aplica_iva VARCHAR(2) DEFAULT 'SI'
        )""")
        conn.commit()
    except Exception as e:
        conn.rollback()

    # Migración en caliente protegida por rollback en caso de fallo
    try:
        cursor.execute("ALTER TABLE productos ADD COLUMN IF NOT EXISTS aplica_iva VARCHAR(2) DEFAULT 'SI';")
        conn.commit()
    except Exception:
        conn.rollback()
    
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS lotes (
            id SERIAL PRIMARY KEY,
            producto_id INTEGER NOT NULL REFERENCES productos(id),
            bodega_id INTEGER NOT NULL REFERENCES bodegas(id),
            lote_proveedor TEXT NOT NULL,
            fecha_fabricacion TEXT,
            fecha_vencimiento TEXT,
            fecha_recepcion TEXT,
            cantidad_actual NUMERIC DEFAULT 0.0,
            costo_unitario NUMERIC DEFAULT 0.0,
            remision_factura TEXT,
            observaciones TEXT
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordenes_compra (
            id SERIAL PRIMARY KEY,
            numero_oc VARCHAR(100) UNIQUE NOT NULL,
            proveedor TEXT NOT NULL,
            estado VARCHAR(50) DEFAULT 'ABIERTA',
            fecha_creacion TEXT NOT NULL
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordenes_compra_items (
            id SERIAL PRIMARY KEY,
            oc_id INTEGER NOT NULL REFERENCES ordenes_compra(id),
            producto_id INTEGER NOT NULL REFERENCES productos(id),
            cantidad_solicitada NUMERIC NOT NULL,
            costo_pactado NUMERIC NOT NULL,
            moneda VARCHAR(10) DEFAULT 'COP',
            trm NUMERIC DEFAULT 1.0,
            subtotal NUMERIC DEFAULT 0.0,
            monto_iva NUMERIC DEFAULT 0.0,
            costo_total NUMERIC DEFAULT 0.0
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos_venta (
            id SERIAL PRIMARY KEY,
            numero_pedido VARCHAR(100) UNIQUE NOT NULL,
            cliente TEXT NOT NULL,
            producto_id INTEGER NOT NULL REFERENCES productos(id),
            cantidad_solicitada NUMERIC NOT NULL,
            precio_unitario NUMERIC NOT NULL,
            vendedor TEXT NOT NULL,
            fecha_pedido TEXT NOT NULL,
            estado VARCHAR(50) DEFAULT 'PENDIENTE',
            subtotal NUMERIC DEFAULT 0.0,
            monto_iva NUMERIC DEFAULT 0.0,
            precio_total NUMERIC DEFAULT 0.0
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kits (
            id SERIAL PRIMARY KEY,
            codigo_kit VARCHAR(100) UNIQUE NOT NULL,
            nombre_kit TEXT NOT NULL
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kit_componentes (
            id SERIAL PRIMARY KEY,
            kit_id INTEGER NOT NULL REFERENCES kits(id),
            componente_id INTEGER NOT NULL REFERENCES productos(id),
            porcentaje_o_cantidad NUMERIC NOT NULL
        )""")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kardex (
            id SERIAL PRIMARY KEY,
            fecha TEXT NOT NULL,
            producto_id INTEGER NOT NULL REFERENCES productos(id),
            bodega_id INTEGER NOT NULL REFERENCES bodegas(id),
            tipo_movimiento VARCHAR(50) NOT NULL,
            cantidad NUMERIC NOT NULL,
            costo_unitario NUMERIC NOT NULL,
            usuario TEXT NOT NULL,
            motivo TEXT,
            lote TEXT,
            documento_ref TEXT
        )""")

        default_users = [
            ("admin", make_hashes("admin123"), "Administrador"),
            ("bodega", make_hashes("bodega123"), "Bodega"),
            ("comercial", make_hashes("comercial123"), "Comercial")
        ]
        for user, pwd, role in default_users:
            cursor.execute("INSERT INTO usuarios (username, password, rol) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING", (user, pwd, role))

        bodegas = ["FINE", "INDUSTRIAL", "MATERIAS PRIMAS", "ENVASES Y DEMÁS"]
        for b in bodegas:
            cursor.execute("INSERT INTO bodegas (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING", (b,))

        conn.commit()
    except Exception as e:
        conn.rollback()

init_db()

# ==========================================
# LÓGICA DE NEGOCIO Y AUTENTICACIÓN
# ==========================================
def login_user(username, password):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE username = %s AND password = %s', (username, make_hashes(password)))
    data = c.fetchone()
    return data

def update_password(username, new_password):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE usuarios SET password = %s WHERE username = %s', (make_hashes(new_password), username))
    conn.commit()
    st.cache_data.clear() # Limpia caché por seguridad

def calcular_costo_promedio_movil(existencia_actual, costo_prom_actual, cant_nueva, costo_nuevo_cop):
    if existencia_actual <= 0:
        return costo_nuevo_cop
    return ((existencia_actual * costo_prom_actual) + (cant_nueva * costo_nuevo_cop)) / (existencia_actual + cant_nueva)

# OPTIMIZACIÓN: Caché de lectura para existencia
@st.cache_data
def obtener_existencia_producto(producto_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT SUM(cantidad_actual) as total FROM lotes WHERE producto_id = %s", (producto_id,))
    res = c.fetchone()['total']
    return float(res) if res else 0.0

# OPTIMIZACIÓN: Caché de lectura para OC pendientes
@st.cache_data
def obtener_oc_pendientes(producto_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT SUM(i.cantidad_solicitada) as oc_cant 
        FROM ordenes_compra_items i 
        JOIN ordenes_compra oc ON i.oc_id = oc.id 
        WHERE i.producto_id = %s AND oc.estado = 'ABIERTA'
    """, (producto_id,))
    res = c.fetchone()['oc_cant']
    return float(res) if res else 0.0

def registrar_recepcion(producto_id, cantidad, lote_prov, fab_date, exp_date, costo_cop_base, moneda, trm, costo_ext, remision, obs, usuario, oc_id=None):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM productos WHERE id = %s", (producto_id,))
    prod = c.fetchone()
    
    existencia_act = obtener_existencia_producto(producto_id)
    costo_prom_act = float(prod['costo_promedio']) if prod['costo_promedio'] else 0.0
    
    nuevo_costo_prom = calcular_costo_promedio_movil(existencia_act, costo_prom_act, cantidad, costo_cop_base)
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("""
        UPDATE productos 
        SET costo_promedio = %s, ultimo_costo = %s, fecha_ultimo_costo = %s 
        WHERE id = %s
    """, (nuevo_costo_prom, costo_cop_base, fecha_hoy, producto_id))
    
    c.execute("""
        INSERT INTO lotes (producto_id, bodega_id, lote_proveedor, fecha_fabricacion, fecha_vencimiento, fecha_recepcion, cantidad_actual, costo_unitario, remision_factura, observaciones)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (producto_id, prod['bodega_id'], lote_prov, fab_date, exp_date, fecha_hoy, cantidad, costo_cop_base, remision, obs))
    
    motivo_txt = f"Recepción Compra ({moneda} TRM: {trm})" if moneda != "COP" else "Recepción Compra"
    c.execute("""
        INSERT INTO kardex (fecha, producto_id, bodega_id, tipo_movimiento, cantidad, costo_unitario, usuario, motivo, lote, documento_ref)
        VALUES (%s, %s, %s, 'ENTRADA', %s, %s, %s, %s, %s, %s)
    """, (fecha_hoy, producto_id, prod['bodega_id'], cantidad, costo_cop_base, usuario, motivo_txt, lote_prov, remision))
    
    if oc_id:
        c.execute("UPDATE ordenes_compra SET estado = 'RECIBIDA' WHERE id = %s", (oc_id,))
        
    conn.commit()
    st.cache_data.clear() # Limpia caché para reflejar los datos actualizados

def registrar_pedido_venta(num_ped, cliente, producto_id, cantidad, precio, vendedor, subtotal, monto_iva, total):
    conn = get_connection()
    c = conn.cursor()
    
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO pedidos_venta (numero_pedido, cliente, producto_id, cantidad_solicitada, precio_unitario, vendedor, fecha_pedido, estado, subtotal, monto_iva, precio_total)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDIENTE', %s, %s, %s)
    """, (num_ped, cliente, producto_id, cantidad, precio, vendedor, fecha_hoy, subtotal, monto_iva, total))
    
    c.execute("UPDATE productos SET comp_venta = comp_venta + %s WHERE id = %s", (cantidad, producto_id))
    conn.commit()
    st.cache_data.clear()

def despachar_pedido_venta(pedido_id, usuario_despacha):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM pedidos_venta WHERE id = %s", (pedido_id,))
    ped = c.fetchone()
    if not ped or ped['estado'] != 'PENDIENTE':
        return False, "El pedido ya fue procesado o no existe."
    
    producto_id = ped['producto_id']
    cant_requerida = float(ped['cantidad_solicitada'])
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("SELECT * FROM productos WHERE id = %s", (producto_id,))
    prod = c.fetchone()
    
    c.execute("SELECT * FROM lotes WHERE producto_id = %s AND cantidad_actual > 0 ORDER BY id ASC", (producto_id,))
    lotes = c.fetchall()
    
    cant_descontada = 0.0
    for l in lotes:
        if cant_descontada >= cant_requerida:
            break
        
        l_cant = float(l['cantidad_actual'])
        faltante = cant_requerida - cant_descontada
        if l_cant <= faltante:
            tomar = l_cant
            c.execute("UPDATE lotes SET cantidad_actual = 0 WHERE id = %s", (l['id'],))
        else:
            tomar = faltante
            c.execute("UPDATE lotes SET cantidad_actual = cantidad_actual - %s WHERE id = %s", (tomar, l['id']))
            
        cant_descontada += tomar
        
        c.execute("""
            INSERT INTO kardex (fecha, producto_id, bodega_id, tipo_movimiento, cantidad, costo_unitario, usuario, motivo, lote, documento_ref)
            VALUES (%s, %s, %s, 'SALIDA', %s, %s, %s, %s, %s, %s)
        """, (fecha_hoy, producto_id, prod['bodega_id'], tomar, prod['costo_promedio'], usuario_despacha, f"Despacho Pedido {ped['numero_pedido']} - Cliente: {ped['cliente']}", l['lote_proveedor'], ped['numero_pedido']))

    c.execute("UPDATE productos SET comp_venta = GREATEST(0.0, comp_venta - %s) WHERE id = %s", (cant_requerida, producto_id))
    c.execute("UPDATE pedidos_venta SET estado = 'DESPACHADO' WHERE id = %s", (pedido_id,))
    
    conn.commit()
    st.cache_data.clear()
    return True, "Despacho realizado con éxito."

def generar_pdf_orden_compra(num_oc, proveedor, items_df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#000080'),
        spaceAfter=10
    )
    
    story.append(Paragraph("<b>ORDEN DE COMPRA OFICIAL</b>", title_style))
    story.append(Paragraph(f"<b>N° Orden:</b> {num_oc}", styles['Normal']))
    story.append(Paragraph(f"<b>Proveedor:</b> {proveedor}", styles['Normal']))
    story.append(Paragraph(f"<b>Fecha Emisión:</b> {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
    story.append(Spacer(1, 15))
    
    data = [["Cód. Proveedor", "Descripción Proveedor", "Cant.", "Moneda", "P. Unitario", "Subtotal", "IVA", "Total"]]
    
    subtotal_gral = 0.0
    iva_gral = 0.0
    total_gral = 0.0
    
    for idx, row in items_df.iterrows():
        sub = float(row['subtotal'])
        iva = float(row['monto_iva'])
        tot = float(row['costo_total'])
        
        subtotal_gral += sub
        iva_gral += iva
        total_gral += tot
        
        data.append([
            str(row['codigo_proveedor']),
            str(row['nombre_proveedor']),
            f"{float(row['cantidad_solicitada']):,.2f}",
            str(row['moneda']),
            f"${float(row['costo_pactado']):,.2f}",
            f"${sub:,.2f}",
            f"${iva:,.2f}",
            f"${tot:,.2f}"
        ])
        
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#000080')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))
    story.append(t)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph(f"<b>SUBTOTAL GENERAL:</b> ${subtotal_gral:,.2f}", styles['Normal']))
    story.append(Paragraph(f"<b>TOTAL IVA (19%):</b> ${iva_gral:,.2f}", styles['Normal']))
    story.append(Paragraph(f"<b>GRAN TOTAL DE LA COMPRA:</b> ${total_gral:,.2f}", styles['Heading3']))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# ==========================================
# FUNCIONES AUXILIARES CON CACHÉ DE DATOS (MÁXIMA VELOCIDAD)
# ==========================================
@st.cache_data
def cargar_tabla_sql(query):
    conn = get_connection()
    return pd.read_sql_query(query, conn)

# ==========================================
# CONTROL DE SESIÓN Y LOGIN
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['username'] = ''
    st.session_state['rol'] = ''

if not st.session_state['logged_in']:
    st.title("🧪 AURANZA SAS - ERP/MRP System")
    st.subheader("🔐 Iniciar Sesión")
    
    with st.form("login_form"):
        user = st.text_input("Usuario")
        pwd = st.text_input("Contraseña", type="password")
        submit_btn = st.form_submit_button("Ingresar")
        
        if submit_btn:
            userdata = login_user(user, pwd)
            if userdata:
                st.session_state['logged_in'] = True
                st.session_state['username'] = userdata['username']
                st.session_state['rol'] = userdata['rol']
                st.success(f"Bienvenido {userdata['username']} ({userdata['rol']})")
                st.rerun()
            else:
                st.error("❌ Usuario o contraseña incorrectos.")
else:
    st.sidebar.title("🧪 AURANZA SAS ERP")
    st.sidebar.markdown(f"👤 **Usuario:** `{st.session_state['username']}`")
    st.sidebar.markdown(f"🛡️ **Rol:** `{st.session_state['rol']}`")
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state['logged_in'] = False
        st.session_state['username'] = ''
        st.session_state['rol'] = ''
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.write("Navegación Módulos:")

    menu = st.sidebar.radio(
        "",
        [
            "📊 Ficha de Producto",
            "🛒 Pedidos y Cotizaciones",
            "📦 Maestro de Productos y Lotes",
            "🏢 Directorio de Proveedores",
            "🧾 Órdenes de Compra y Recepción",
            "🧪 Kits y Ensambles",
            "🚨 Requerimiento Comercial (MRP)",
            "📜 Kardex e Historial",
            "⚙️ Mi Cuenta y Configuración"
        ]
    )

    conn = get_connection()
    rol = st.session_state['rol']

    @st.cache_data
    def obtener_notificacion_pedidos():
        q_pend = """
            SELECT p.numero_pedido, p.cliente, pr.nombre_au, p.cantidad_solicitada, p.vendedor 
            FROM pedidos_venta p 
            JOIN productos pr ON p.producto_id = pr.id 
            WHERE p.estado = 'PENDIENTE'
        """
        return cargar_tabla_sql(q_pend)

    try:
        df_p_pend = obtener_notificacion_pedidos()
        if not df_p_pend.empty:
            st.warning(f"🚨 **NOTIFICACIÓN GLOBAL:** Hay **{len(df_p_pend)} Pedido(s) de Venta PENDIENTE(S)** por despachar / facturar.")
            with st.expander("Ver lista de pedidos pendientes por despachar"):
                st.dataframe(df_p_pend, use_container_width=True)
    except Exception:
        pass

    if menu == "📊 Ficha de Producto":
        st.title("📊 Consulta General de Producto / Inventario")
        busqueda = st.text_input("🔍 Buscar por Código AU, Código Proveedor o Nombre:")
        
        query = "SELECT p.*, b.nombre as nombre_bodega FROM productos p JOIN bodegas b ON p.bodega_id = b.id"
        try:
            df_prods = cargar_tabla_sql(query)
        except Exception:
            df_prods = pd.DataFrame()
        
        if busqueda and not df_prods.empty:
            df_prods = df_prods[
                df_prods['codigo_au'].str.contains(busqueda, case=False, na=False) |
                df_prods['codigo_proveedor'].str.contains(busqueda, case=False, na=False) |
                df_prods['nombre_au'].str.contains(busqueda, case=False, na=False)
            ]
            
        if not df_prods.empty:
            prod_sel_id = st.selectbox(
                "Seleccione un producto del resultado:", 
                df_prods['id'].tolist(), 
                index=None,
                placeholder="-- Seleccione un producto para ver la ficha --",
                format_func=lambda x: f"{df_prods[df_prods['id']==x]['codigo_au'].values[0]} | {df_prods[df_prods['id']==x]['nombre_au'].values[0]} (Prov: {df_prods[df_prods['id']==x]['codigo_proveedor'].values[0]})"
            )
            
            if prod_sel_id:
                p = df_prods[df_prods['id'] == prod_sel_id].iloc[0]
                existencia_total = obtener_existencia_producto(prod_sel_id)
                comp_oc = obtener_oc_pendientes(prod_sel_id)
                
                c = conn.cursor()
                c.execute("SELECT SUM(cantidad) as ent FROM kardex WHERE producto_id = %s AND tipo_movimiento = 'ENTRADA'", (prod_sel_id,))
                r_ent = c.fetchone()['ent']
                tot_entradas = float(r_ent) if r_ent else 0.0
                
                c.execute("SELECT SUM(cantidad) as sal FROM kardex WHERE producto_id = %s AND tipo_movimiento IN ('SALIDA', 'ENSAMBLE', 'MERMA')", (prod_sel_id,))
                r_sal = c.fetchone()['sal']
                tot_salidas = float(r_sal) if r_sal else 0.0

                comp_venta = float(p['comp_venta']) if p['comp_venta'] else 0.0
                comp_op = float(p['comp_op']) if p['comp_op'] else 0.0
                comp_requisicion = float(p['comp_requisicion']) if p['comp_requisicion'] else 0.0
                punto_pedido = float(p['punto_pedido']) if p['punto_pedido'] else 0.0
                nivel_maximo = float(p['nivel_maximo']) if p['nivel_maximo'] else 0.0
                nivel_minimo = float(p['nivel_minimo']) if p['nivel_minimo'] else 0.0
                costo_promedio = float(p['costo_promedio']) if p['costo_promedio'] else 0.0
                ultimo_costo = float(p['ultimo_costo']) if p['ultimo_costo'] else 0.0

                disp_total = existencia_total - comp_venta - comp_op + comp_oc

                st.markdown(f"""
                <div style="background-color:#000080; color:#FFFFFF; font-family:monospace; padding:15px; border-radius:5px;">
                -----------------------------------------------------------------------------------------------------<br>
                | Item &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{p['codigo_au']}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>{str(p['nombre_au']).upper()}</b><br>
                | Cód Proveedor: <b>{p['codigo_proveedor']}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; PROVEEDOR: <b>{str(p['proveedor']).upper()}</b><br>
                | Localizacion : <b>{str(p['nombre_bodega']).upper()}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; APLICA IVA: <b>{p.get('aplica_iva', 'SI')}</b><br>
                -----------------------------------------------------------------------------------------------------<br>
                | U.M: <b>{p['unidad_medida']}</b> Clasif.: <b>{p['categoria']} / {p['linea']}</b> &nbsp;|&nbsp; Acumulados Desde &nbsp;&nbsp;&nbsp;&nbsp;: AURANZA-2026<br>
                +-----------------------------------------------+ Total Entradas &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {tot_entradas:,.3f}<br>
                | Existencia Actual : <b>{existencia_total:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Total Salidas &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {tot_salidas:,.3f}<br>
                | Comp. en Venta &nbsp;&nbsp;&nbsp;&nbsp;: <b>{comp_venta:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;+------------------------------------+<br>
                | Comp. en O.P. &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{comp_op:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Costo Prom. Base &nbsp;&nbsp;&nbsp;&nbsp;: $ {costo_promedio:,.2f}<br>
                | Comp. Requisicion : <b>{comp_requisicion:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Ultimo Costo Base &nbsp;&nbsp;&nbsp;: $ {ultimo_costo:,.2f}<br>
                | Comp. en O.C. &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{comp_oc:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Fecha Ult. Costo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {p['fecha_ultimo_costo'] if p['fecha_ultimo_costo'] else 'N/A'}<br>
                | <b>Total Disponible &nbsp;: {disp_total:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;+------------------------------------+<br>
                -----------------------------------------------------------------------------------------------------<br>
                | Punto Pedido &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{punto_pedido:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Nivel Maximo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {nivel_maximo:,.3f}<br>
                | Cantidad a Pedir &nbsp;&nbsp;: <b>{max(0.0, punto_pedido - disp_total):,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Nivel Minimo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {nivel_minimo:,.3f}<br>
                -----------------------------------------------------------------------------------------------------
                </div>
                """, unsafe_allow_html=True)
                
                st.subheader("📦 Trazabilidad por Lotes Activos")
                df_lotes = cargar_tabla_sql(f"SELECT lote_proveedor, cantidad_actual, fecha_fabricacion, fecha_vencimiento, costo_unitario, remision_factura, observaciones FROM lotes WHERE producto_id = {prod_sel_id} AND cantidad_actual > 0")
                st.dataframe(df_lotes, use_container_width=True)
            else:
                st.info("👆 Por favor seleccione un producto del desplegable arriba para visualizar su ficha técnica e inventarios.")
        else:
            st.warning("⚠️ No se encontraron productos registrados.")

    elif menu == "🛒 Pedidos y Cotizaciones":
        st.title("🛒 Módulo de Pedidos de Venta, Cotizaciones y Despachos")
        
        sub_vta = st.radio("Acción a realizar:", ["➕ Montar Nuevo Pedido / Cotización", "🚚 Control de Despachos y Facturación"], horizontal=True)
        
        if sub_vta == "➕ Montar Nuevo Pedido / Cotización":
            st.subheader("Registrar Orden de Pedido Comercial / Cotización", anchor=False)
            if rol not in ["Administrador", "Comercial"]:
                st.warning("⚠️ Perfil sin autorización para montar pedidos de venta.")
            else:
                try:
                    df_prods_vta = cargar_tabla_sql("SELECT id, codigo_au, nombre_au, precio_venta, aplica_iva FROM productos")
                except Exception:
                    df_prods_vta = pd.DataFrame()
                
                if df_prods_vta.empty:
                    st.warning("⚠️ No hay productos registrados para vender.")
                else:
                    with st.form("form_nuevo_pedido"):
                        c_p1, c_p2 = st.columns(2)
                        num_ped = c_p1.text_input("Número / Código de Pedido (ej: PED-001):")
                        cliente = c_p2.text_input("Nombre del Cliente:")
                        
                        prod_ped_id = st.selectbox("Producto / Ensamble a Vender:", df_prods_vta['id'].tolist(), format_func=lambda x: f"{df_prods_vta[df_prods_vta['id']==x]['codigo_au'].values[0]} - {df_prods_vta[df_prods_vta['id']==x]['nombre_au'].values[0]}")
                        
                        p_sel_info = df_prods_vta[df_prods_vta['id']==prod_ped_id].iloc[0]
                        stock_disp = obtener_existencia_producto(prod_ped_id)
                        
                        c_p3, c_p4 = st.columns(2)
                        cant_ped = c_p3.number_input("Cantidad Requerida (KG/Unidades):", min_value=0.1, value=10.0)
                        precio_ped_base = c_p4.number_input("Precio Base Unitario ($ COP sin IVA):", value=float(p_sel_info['precio_venta']) if p_sel_info['precio_venta'] else 0.0)
                        
                        subtotal = cant_ped * precio_ped_base
                        aplica_iva = p_sel_info.get('aplica_iva', 'SI') == 'SI'
                        monto_iva = subtotal * 0.19 if aplica_iva else 0.0
                        total_pedido = subtotal + monto_iva
                        
                        st.markdown(f"""
                        * **Subtotal Base:** ${subtotal:,.2f} COP
                        * **IVA Calculado (19%):** ${monto_iva:,.2f} COP
                        * **TOTAL PEDIDO / COTIZACIÓN:** `${total_pedido:,.2f} COP`
                        """)
                        
                        st.info(f"📊 **Stock Físico Actual:** {stock_disp:,.2f} KG")
                        
                        if st.form_submit_button("Guardar y Comprometer Inventario"):
                            if not num_ped or not cliente:
                                st.error("❌ Indique el número de pedido y el cliente.")
                            else:
                                try:
                                    registrar_pedido_venta(num_ped, cliente, prod_ped_id, cant_ped, precio_ped_base, st.session_state['username'], subtotal, monto_iva, total_pedido)
                                    st.success(f"✅ Pedido {num_ped} registrado. Se sumó {cant_ped} KG a Comprometido en Venta.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al registrar pedido: {e}")

        elif sub_vta == "🚚 Control de Despachos y Facturación":
            st.subheader("Despacho e Impacto en Inventario / Kardex", anchor=False)
            try:
                df_pedidos = cargar_tabla_sql("""
                    SELECT p.id, p.numero_pedido, p.cliente, pr.codigo_au, pr.nombre_au, p.cantidad_solicitada, p.precio_unitario, p.subtotal, p.monto_iva, p.precio_total, p.vendedor, p.fecha_pedido, p.estado
                    FROM pedidos_venta p
                    JOIN productos pr ON p.producto_id = pr.id
                    ORDER BY p.id DESC
                """)
                
                if df_pedidos.empty:
                    st.info("No hay pedidos de venta registrados.")
                else:
                    st.dataframe(df_pedidos, use_container_width=True)
                    
                    st.markdown("---")
                    st.subheader("Ejecutar Despacho Físico (Bodega / Admin)")
                    pedidos_pendientes = df_pedidos[df_pedidos['estado'] == 'PENDIENTE']
                    
                    if pedidos_pendientes.empty:
                        st.success("✨ Todos los pedidos están despachados al día.")
                    else:
                        ped_to_desp = st.selectbox("Seleccionar Pedido Pendiente por Despachar:", pedidos_pendientes['id'].tolist(), format_func=lambda x: f"Pedido {pedidos_pendientes[pedidos_pendientes['id']==x]['numero_pedido'].values[0]} - Cliente: {pedidos_pendientes[pedidos_pendientes['id']==x]['cliente'].values[0]} ({pedidos_pendientes[pedidos_pendientes['id']==x]['cantidad_solicitada'].values[0]} KG)")
                        
                        if st.button("🚀 Confirmar Despacho Físico y Facturar"):
                            if rol not in ["Administrador", "Bodega"]:
                                st.error("❌ Solo los roles Bodega o Administrador pueden despachar pedidos.")
                            else:
                                ok, msg = despachar_pedido_venta(ped_to_desp, st.session_state['username'])
                                if ok:
                                    st.success(f"✅ {msg}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {msg}")
            except Exception:
                st.info("Aún no hay módulo de pedidos activo.")

    elif menu == "📦 Maestro de Productos y Lotes":
        st.title("📦 Crear y Administrar Productos")
        
        if rol != "Administrador":
            st.warning("⚠️ Rol limitado: La creación y modificación de productos es función exclusiva del rol **Administrador**.")
        else:
            # Cargar lista actualizada de proveedores desde la BD
            try:
                df_provs_db = cargar_tabla_sql("SELECT nombre FROM proveedores ORDER BY nombre ASC")
                lista_proveedores = df_provs_db['nombre'].tolist() if not df_provs_db.empty else []
            except Exception:
                lista_proveedores = []

            with st.form("crear_producto"):
                st.subheader("Formulario de Creación de Producto AURANZA", anchor=False)
                c1, c2, c3 = st.columns(3)
                codigo_au = c1.text_input("Código AU Interno (ej: AUH0001):")
                codigo_prov = c2.text_input("Código Proveedor (ej: XB0102):")
                nombre_au = c3.text_input("Nombre AU (ej: BAMBU):")
                
                c4, c5, c6 = st.columns(3)
                nombre_prov = c4.text_input("Nombre en Proveedor (ej: BAMBOO):")
                
                # REQUERIMIENTO: Nombre del Proveedor en Lista Desplegable
                if lista_proveedores:
                    proveedor = c5.selectbox("Nombre del Proveedor:", lista_proveedores)
                else:
                    proveedor = c5.selectbox("Nombre del Proveedor:", ["-- No hay proveedores creados --"])
                    st.caption("⚠️ Primero debes crear un proveedor en el menú '🏢 Directorio de Proveedores'.")

                bodega_id = c6.selectbox("Bodega Principal Asignada:", [1, 2, 3, 4], format_func=lambda x: ["FINE", "INDUSTRIAL", "MATERIAS PRIMAS", "ENVASES Y DEMÁS"][x-1])
                
                c7, c8, c9 = st.columns(3)
                categoria = c7.selectbox("Categoría:", ["FRAGANCIA", "MATERIA PRIMA", "ENVASE", "EMPAQUE"])
                linea = c8.selectbox("Línea:", ["Fragancias Homecare", "Fragancias Capilares", "Fragancias Óleo", "Fragancias Reeds", "Perfumería Fina Masculina", "Perfumería Fina Femenina", "Perfumería Fina Unisex", "Envases", "Insumos"])
                precio_vta = c9.number_input("Precio de Venta Base ($):", min_value=0.0)
                
                c10, c11, c12, c13 = st.columns(4)
                pt_pedido = c10.number_input("Punto de Pedido:", min_value=0.0)
                nv_min = c11.number_input("Nivel Mínimo:", min_value=0.0)
                nv_max = c12.number_input("Nivel Máximo:", min_value=0.0)
                
                aplica_iva = c13.selectbox("Aplica IVA (19%):", ["SI", "NO"], index=0)
                
                btn_crear = st.form_submit_button("Guardar Producto")
                if btn_crear:
                    if not lista_proveedores or proveedor == "-- No hay proveedores creados --":
                        st.error("❌ Debes seleccionar un proveedor válido antes de crear el producto.")
                    else:
                        try:
                            c = conn.cursor()
                            c.execute("""
                                INSERT INTO productos (codigo_au, codigo_proveedor, nombre_au, nombre_proveedor, proveedor, categoria, linea, bodega_id, precio_venta, punto_pedido, nivel_minimo, nivel_maximo, aplica_iva)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (codigo_au, codigo_prov, nombre_au, nombre_prov, proveedor, categoria, linea, bodega_id, precio_vta, pt_pedido, nv_min, nv_max, aplica_iva))
                            conn.commit()
                            st.cache_data.clear()
                            st.success(f"✅ Producto {codigo_au} - {nombre_au} creado exitosamente con IVA: {aplica_iva}")
                        except Exception as e:
                            st.error(f"Error al crear producto: {e}")

        st.subheader("Inventario Consolidado por Productos", anchor=False)
        try:
            df_prods_all = cargar_tabla_sql("SELECT p.codigo_au, p.codigo_proveedor, p.nombre_au, p.proveedor, b.nombre as bodega, p.costo_promedio, p.ultimo_costo, p.precio_venta, p.aplica_iva FROM productos p JOIN bodegas b ON p.bodega_id = b.id")
            st.dataframe(df_prods_all, use_container_width=True)
        except Exception:
            st.info("Aún no hay productos registrados.")

    elif menu == "🏢 Directorio de Proveedores":
        st.title("🏢 Gestión y Directorio de Proveedores", anchor=False)
        
        if rol == "Administrador":
            with st.expander("➕ Registrar Nuevo Proveedor"):
                with st.form("form_proveedor"):
                    c_pr1, c_pr2 = st.columns(2)
                    nom_prov = c_pr1.text_input("Nombre / Razon Social:")
                    nit_prov = c_pr2.text_input("NIT / Documento:")
                    
                    c_pr3, c_pr4 = st.columns(2)
                    contacto_prov = c_pr3.text_input("Persona de Contacto:")
                    tel_prov = c_pr4.text_input("Teléfono:")
                    email_prov = st.text_input("Correo Electrónico:")
                    
                    if st.form_submit_button("Guardar Proveedor"):
                        if not nom_prov:
                            st.error("❌ Ingrese el nombre del proveedor.")
                        else:
                            try:
                                c = conn.cursor()
                                c.execute("INSERT INTO proveedores (nombre, nit, contacto, telefono, email) VALUES (%s, %s, %s, %s, %s)", (nom_prov, nit_prov, contacto_prov, tel_prov, email_prov))
                                conn.commit()
                                st.cache_data.clear()
                                st.success(f"✅ Proveedor {nom_prov} registrado correctamente.")
                            except Exception as e:
                                st.error(f"Error al guardar proveedor: {e}")

        st.subheader("Listado de Proveedores Registrados", anchor=False)
        try:
            df_provs = cargar_tabla_sql("SELECT nombre, nit, contacto, telefono, email FROM proveedores")
            st.dataframe(df_provs, use_container_width=True)
        except Exception:
            st.info("Aún no hay proveedores registrados.")

    elif menu == "🧾 Órdenes de Compra y Recepción":
        st.title("🧾 Gestión de Compras y Recepciones", anchor=False)
        
        sub_oc = st.radio("Acción a realizar:", ["Emitir Órden de Compra (OC)", "📦 Recepción de Mercancía en Bodega"], horizontal=True)

        if sub_oc == "Emitir Órden de Compra (OC)":
            st.subheader("Generar Nueva Orden de Compra", anchor=False)
            if rol not in ["Administrador"]:
                st.warning("⚠️ Emisión de Compras restringida a perfil Administrador.")
            else:
                try:
                    df_prods = cargar_tabla_sql("SELECT id, codigo_au, codigo_proveedor, nombre_au, nombre_proveedor, proveedor, aplica_iva FROM productos")
                except Exception:
                    df_prods = pd.DataFrame()
                
                if df_prods.empty:
                    st.warning("⚠️ Primero cree productos en el menú 'Maestro de Productos y Lotes'.")
                else:
                    num_oc = st.text_input("Número de OC (ej: OC-0001):")
                    prod_oc_id = st.selectbox("Seleccionar Producto:", df_prods['id'].tolist(), format_func=lambda x: f"{df_prods[df_prods['id']==x]['nombre_au'].values[0]} | Proveedor: {df_prods[df_prods['id']==x]['proveedor'].values[0]}")
                    
                    prod_info = df_prods[df_prods['id']==prod_oc_id].iloc[0]
                    
                    col_a, col_b, col_c = st.columns(3)
                    cant_oc = col_a.number_input("Cantidad a Solicitar (KG/Unidades):", min_value=0.1)
                    moneda_oc = col_b.selectbox("Moneda O.C.:", ["COP", "USD", "EUR"])
                    trm_oc = col_c.number_input("TRM Proyectada (COP):", value=4100.0 if moneda_oc != "COP" else 1.0)
                    
                    costo_unit_ext = st.number_input(f"Costo Base Unitario sin IVA en {moneda_oc}:", min_value=0.0)
                    costo_cop_base = costo_unit_ext * trm_oc if moneda_oc != "COP" else costo_unit_ext
                    
                    subtotal = cant_oc * costo_cop_base
                    aplica_iva = prod_info.get('aplica_iva', 'SI') == 'SI'
                    monto_iva = subtotal * 0.19 if aplica_iva else 0.0
                    costo_total = subtotal + monto_iva
                    
                    st.markdown("### 💰 Desglose Financiero O.C.")
                    st.markdown(f"""
                    * **Subtotal Base Costo:** ${subtotal:,.2f} COP
                    * **Monto Impuesto IVA (19%):** ${monto_iva:,.2f} COP
                    * **COSTO TOTAL FACTURA PROVEEDOR:** `${costo_total:,.2f} COP`
                    """)

                    st.info(f"📋 **Documento Proveedor:** {prod_info['codigo_proveedor']} - {prod_info['nombre_proveedor']} | **Aplica IVA:** {prod_info['aplica_iva']}")
                    
                    if st.button("Emitir Orden de Compra y Generar PDF"):
                        c = conn.cursor()
                        c.execute("INSERT INTO ordenes_compra (numero_oc, proveedor, fecha_creacion) VALUES (%s, %s, %s) RETURNING id", (num_oc, prod_info['proveedor'], datetime.now().strftime("%Y-%m-%d")))
                        oc_id = c.fetchone()['id']
                        c.execute("""
                            INSERT INTO ordenes_compra_items (oc_id, producto_id, cantidad_solicitada, costo_pactado, moneda, trm, subtotal, monto_iva, costo_total)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (oc_id, prod_oc_id, cant_oc, costo_cop_base, moneda_oc, trm_oc, subtotal, monto_iva, costo_total))
                        conn.commit()
                        st.cache_data.clear()
                        st.success(f"✅ OC {num_oc} emitida correctamente.")
                        
                        df_pdf_item = pd.DataFrame([{
                            'codigo_proveedor': prod_info['codigo_proveedor'],
                            'nombre_proveedor': prod_info['nombre_proveedor'],
                            'cantidad_solicitada': cant_oc,
                            'moneda': moneda_oc,
                            'costo_pactado': costo_unit_ext,
                            'subtotal': subtotal,
                            'monto_iva': monto_iva,
                            'costo_total': costo_total
                        }])
                        pdf_bytes = generar_pdf_orden_compra(num_oc, prod_info['proveedor'], df_pdf_item)
                        st.download_button("📄 Descargar Orden de Compra (PDF Filtrado Proveedor)", data=pdf_bytes, file_name=f"OC_{num_oc}.pdf", mime="application/pdf")

        elif sub_oc == "📦 Recepción de Mercancía en Bodega":
            st.subheader("Entrada de Mercancía a Bodega (Recepción)", anchor=False)
            if rol not in ["Administrador", "Bodega"]:
                st.warning("⚠️ Modulo de recepción reservado para perfiles Bodega o Administrador.")
            else:
                try:
                    df_ocs = cargar_tabla_sql("""
                        SELECT oc.id, oc.numero_oc, oc.proveedor, i.producto_id, i.cantidad_solicitada, i.costo_pactado, i.moneda, i.trm, i.subtotal, i.monto_iva, i.costo_total
                        FROM ordenes_compra oc 
                        JOIN ordenes_compra_items i ON oc.id = i.oc_id 
                        WHERE oc.estado = 'ABIERTA'
                    """)
                except Exception:
                    df_ocs = pd.DataFrame()
                
                if df_ocs.empty:
                    st.info("No hay Órdenes de Compra abiertas pendientes por recibir.")
                else:
                    oc_sel = st.selectbox("Seleccionar OC por Recibir:", df_ocs['id'].tolist(), format_func=lambda x: f"OC: {df_ocs[df_ocs['id']==x]['numero_oc'].values[0]} - Prov: {df_ocs[df_ocs['id']==x]['proveedor'].values[0]}")
                    item_oc = df_ocs[df_ocs['id']==oc_sel].iloc[0]
                    
                    with st.form("form_rx"):
                        st.write(f"Recibiendo producto ID: {item_oc['producto_id']} | Cantidad solicitada: {item_oc['cantidad_solicitada']} KG")
                        
                        c_rx1, c_rx2 = st.columns(2)
                        cant_rx = c_rx1.number_input("Cantidad Real Recibida (KG):", value=float(item_oc['cantidad_solicitada']))
                        remision = c_rx2.text_input("Documento / Remisión / Factura Proveedor:")
                        
                        st.markdown("---")
                        st.write("<b>Casillas de Validación Cruzada de Facturación</b>", unsafe_allow_html=True)
                        cm1, cm2, cm3 = st.columns(3)
                        moneda_rx = cm1.selectbox("Moneda Factura:", ["COP", "USD", "EUR"], index=["COP", "USD", "EUR"].index(item_oc['moneda']))
                        trm_rx = cm2.number_input("TRM Aplicada Factura:", value=float(item_oc['trm']))
                        
                        c_sub, c_iva, c_tot = st.columns(3)
                        rx_subtotal = c_sub.number_input("Subtotal Costo Facturado ($):", value=float(item_oc['subtotal']))
                        rx_iva = c_iva.number_input("Monto IVA Facturado ($):", value=float(item_oc['monto_iva']))
                        rx_total = c_tot.number_input("TOTAL FACTURA PROVEEDOR ($):", value=float(item_oc['costo_total']))
                        
                        costo_cop_base_unit = rx_subtotal / cant_rx if cant_rx > 0 else 0.0
                        st.success(f"💰 **Costo Base Unitario de Entrada a Valoración (sin IVA):** ${costo_cop_base_unit:,.2f} COP / KG")
                        
                        st.markdown("---")
                        lote_prov = st.text_input("Número de Lote del Proveedor:")
                        
                        cd1, cd2 = st.columns(2)
                        fab_date = cd1.date_input("Fecha de Fabricación:")
                        exp_date = cd2.date_input("Fecha de Vencimiento:")
                        
                        obs_rx = st.text_area("Observaciones de Recepción:")
                        
                        if st.form_submit_button("Confirmar Entrada y Actualizar Costo Promedio Móvil"):
                            registrar_recepcion(int(item_oc['producto_id']), cant_rx, lote_prov, str(fab_date), str(exp_date), costo_cop_base_unit, moneda_rx, trm_rx, costo_cop_base_unit, remision, obs_rx, st.session_state['username'], oc_id=int(item_oc['id']))
                            st.success("✅ Entrada registrada exitosamente. Costo promedio ponderado móvil actualizado.")

    elif menu == "🧪 Kits y Ensambles":
        st.title("🧪 Creación y Ensamble de Kits", anchor=False)
        
        st.subheader("Fórmulas de Ensamble y Costo Teórico Actualizado", anchor=False)
        try:
            df_prods = cargar_tabla_sql("SELECT id, codigo_au, nombre_au, costo_promedio FROM productos")
        except Exception:
            df_prods = pd.DataFrame()
        
        if df_prods.empty:
            st.warning("⚠️ Debe registrar productos en 'Maestro de Productos y Lotes' para armar fórmulas.")
        else:
            if rol == "Administrador":
                with st.expander("➕ Crear / Configurar Fórmula de Kit"):
                    cod_kit = st.text_input("Código del Kit / Producto Final (ej: AU0010):")
                    nom_kit = st.text_input("Nombre Comercial Kit (ej: FRAGANCIA BAMBU 1KG):")
                    
                    st.write("Seleccione Componentes Químicos (Base para 1 KG):")
                    comp1 = st.selectbox("Componente 1:", df_prods['id'].tolist(), format_func=lambda x: f"{df_prods[df_prods['id']==x]['codigo_au'].values[0]} - {df_prods[df_prods['id']==x]['nombre_au'].values[0]}")
                    prop1 = st.number_input("Cantidad Componente 1 (KG):", value=0.6)
                    
                    comp2 = st.selectbox("Componente 2:", df_prods['id'].tolist(), format_func=lambda x: f"{df_prods[df_prods['id']==x]['codigo_au'].values[0]} - {df_prods[df_prods['id']==x]['nombre_au'].values[0]}")
                    prop2 = st.number_input("Cantidad Componente 2 (KG):", value=0.3)

                    comp3 = st.selectbox("Componente 3:", df_prods['id'].tolist(), format_func=lambda x: f"{df_prods[df_prods['id']==x]['codigo_au'].values[0]} - {df_prods[df_prods['id']==x]['nombre_au'].values[0]}")
                    prop3 = st.number_input("Cantidad Componente 3 (KG):", value=0.1)

                    if st.button("Guardar Fórmula Kit"):
                        c = conn.cursor()
                        c.execute("INSERT INTO kits (codigo_kit, nombre_kit) VALUES (%s, %s) RETURNING id", (cod_kit, nom_kit))
                        kit_id = c.fetchone()['id']
                        c.execute("INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad) VALUES (%s, %s, %s)", (kit_id, comp1, prop1))
                        c.execute("INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad) VALUES (%s, %s, %s)", (kit_id, comp2, prop2))
                        c.execute("INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad) VALUES (%s, %s, %s)", (kit_id, comp3, prop3))
                        conn.commit()
                        st.cache_data.clear()
                        st.success("✅ Fórmula de Kit guardada.")

        st.subheader("Análisis de Costo y Margen Teórico por Kit", anchor=False)
        try:
            df_kits_list = cargar_tabla_sql("SELECT * FROM kits")
            for idx, k_item in df_kits_list.iterrows():
                df_comp_k = cargar_tabla_sql(f"""
                    SELECT kc.porcentaje_o_cantidad, p.costo_promedio, p.nombre_au
                    FROM kit_componentes kc
                    JOIN productos p ON kc.componente_id = p.id
                    WHERE kc.kit_id = {k_item['id']}
                """)
                
                costo_mezcla_kg = sum(df_comp_k['porcentaje_o_cantidad'] * df_comp_k['costo_promedio'])
                st.info(f"🧪 **{k_item['codigo_kit']} - {k_item['nombre_kit']}** | Costo Promedio Móvil Mezcla: **${costo_mezcla_kg:,.2f} COP / KG**")
        except Exception:
            st.info("Aún no hay kits creados.")

    elif menu == "🚨 Requerimiento Comercial (MRP)":
        st.title("🚨 Motor MRP: Análisis de Materias Primas y Empaques", anchor=False)
        
        try:
            df_kits = cargar_tabla_sql("SELECT * FROM kits")
        except Exception:
            df_kits = pd.DataFrame()

        if df_kits.empty:
            st.warning("⚠️ No existen Kits registrados para simular el MRP. Regístrelos en 'Kits y Ensambles'.")
        else:
            kit_sel = st.selectbox("Seleccionar Kit a Comercializar:", df_kits['id'].tolist(), format_func=lambda x: f"{df_kits[df_kits['id']==x]['codigo_kit'].values[0]} - {df_kits[df_kits['id']==x]['nombre_kit'].values[0]}")
            cant_solicitada = st.number_input("Cantidad Requerida por Cliente (KG):", value=300.0)
            
            if st.button("🔍 Evaluar Disponibilidad y Generar Requerimientos"):
                st.subheader("1. Evaluación de Materias Primas")
                df_comps = cargar_tabla_sql(f"""
                    SELECT kc.componente_id, p.codigo_au, p.nombre_au, kc.porcentaje_o_cantidad, p.costo_promedio
                    FROM kit_componentes kc
                    JOIN productos p ON kc.componente_id = p.id
                    WHERE kc.kit_id = {kit_sel}
                """)
                
                costo_mezcla_total = 0.0
                
                for idx, row in df_comps.iterrows():
                    necesario = float(row['porcentaje_o_cantidad']) * cant_solicitada
                    disponible_fisico = obtener_existencia_producto(row['componente_id'])
                    oc_pendientes = obtener_oc_pendientes(row['componente_id'])
                    disponible_neto = disponible_fisico + oc_pendientes
                    
                    costo_comp = necesario * float(row['costo_promedio']) if row['costo_promedio'] else 0.0
                    costo_mezcla_total += costo_comp
                    
                    if disponible_neto >= necesario:
                        st.success(f"🟢 **{row['nombre_au']} ({row['codigo_au']})**: Requerido: {necesario:.2f} KG | Stock Físico: {disponible_fisico:.2f} KG | OC Abiertas: {oc_pendientes:.2f} KG")
                    else:
                        faltante_neto = necesario - disponible_neto
                        st.error(f"🔴 **{row['nombre_au']} ({row['codigo_au']})**: Requerido: {necesario:.2f} KG | Stock Físico: {disponible_fisico:.2f} KG | OC Abiertas: {oc_pendientes:.2f} KG | **FALTANTE NETO A COMPRAR: {faltante_neto:.2f} KG**")
                
                st.subheader("2. Regla de Empaques y Evaluación en Bodega 4", anchor=False)
                if cant_solicitada <= 2:
                    unidades_envase = 1
                    tipo_envase = "Envase 2 KG"
                elif cant_solicitada <= 5:
                    unidades_envase = 1
                    tipo_envase = "Envase 5 KG"
                else:
                    unidades_envase = int(cant_solicitada // 20) + (1 if cant_solicitada % 20 != 0 else 0)
                    tipo_envase = "Envase 20 KG"
                    
                st.warning(f"📦 Requerimiento Logístico: **{unidades_envase} Unidades de {tipo_envase} + {unidades_envase} Tapas + {unidades_envase} Tapones**.")
                st.metric("Costo Estimado Mezcla Materias Primas", f"${costo_mezcla_total:,.2f} COP")

    elif menu == "📜 Kardex e Historial":
        st.title("📜 Trazabilidad Completa / Kardex Auditable", anchor=False)
        try:
            df_kardex = cargar_tabla_sql("""
                SELECT k.fecha, p.codigo_au, p.nombre_au, b.nombre as bodega, k.tipo_movimiento, k.cantidad, k.costo_unitario, k.usuario, k.motivo, k.lote, k.documento_ref
                FROM kardex k
                LEFT JOIN productos p ON k.producto_id = p.id
                LEFT JOIN bodegas b ON k.bodega_id = b.id
                ORDER BY k.id DESC
            """)
            if df_kardex.empty:
                st.info("Aún no hay movimientos registrados en el Kardex.")
            else:
                st.dataframe(df_kardex, use_container_width=True)
        except Exception:
            st.info("Aún no se han generado registros en el Kardex.")

    elif menu == "⚙️ Mi Cuenta y Configuración":
        st.title("⚙️ Gestión de Claves y Usuarios", anchor=False)
        
        st.subheader("🔑 Cambiar mi Contraseña", anchor=False)
        with st.form("form_cambiar_clave"):
            pwd_actual = st.text_input("Contraseña Actual", type="password")
            pwd_nueva = st.text_input("Nueva Contraseña", type="password")
            pwd_confirm = st.text_input("Confirmar Nueva Contraseña", type="password")
            
            if st.form_submit_button("Actualizar mi Contraseña"):
                user_check = login_user(st.session_state['username'], pwd_actual)
                if not user_check:
                    st.error("❌ La contraseña actual no es correcta.")
                elif pwd_nueva != pwd_confirm:
                    st.error("❌ La nueva contraseña y su confirmación no coinciden.")
                elif len(pwd_nueva) < 4:
                    st.error("⚠️ La contraseña debe tener al menos 4 caracteres.")
                else:
                    update_password(st.session_state['username'], pwd_nueva)
                    st.success("✅ ¡Contraseña actualizada exitosamente!")

        if rol == "Administrador":
            st.markdown("---")
            st.subheader("🛡️ Administración de Usuarios (Solo Administrador)")
            c_usr = conn.cursor()
            c_usr.execute("SELECT id, username, rol FROM usuarios")
            users_list = c_usr.fetchall()
            
            df_users = pd.DataFrame(users_list, columns=['ID', 'Usuario', 'Rol'])
            st.dataframe(df_users, use_container_width=True)
            
            with st.expander("Resetear contraseña a otro usuario"):
                usr_to_reset = st.selectbox("Seleccionar usuario:", df_users['Usuario'].tolist())
                new_pass_admin = st.text_input("Nueva Contraseña para este usuario", type="password", key="admin_reset")
                if st.button("Resetear Contraseña"):
                    if len(new_pass_admin) >= 4:
                        update_password(usr_to_reset, new_pass_admin)
                        st.success(f"✅ Contraseña de `{usr_to_reset}` actualizada correctamente.")
                    else:
                        st.error("La contraseña debe tener al menos 4 caracteres.")
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

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

@st.cache_resource
def get_connection():
    try:
        conn = psycopg2.connect(
            host=st.secrets["postgres"]["host"],
            port=st.secrets["postgres"]["port"],
            database=st.secrets["postgres"]["dbname"],
            user=st.secrets["postgres"]["user"],
            password=st.secrets["postgres"]["password"],
            cursor_factory=psycopg2.extras.DictCursor,
            connect_timeout=10
        )
        return conn
    except Exception as e:
        st.error(f"❌ Error crítico de conexión a Supabase: {e}")
        st.stop()

def ejecutar_sql_seguro(query, params=None):
    """Ejecuta una sentencia SQL en una transacción aislada para evitar abortar el bloque completo."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cursor.close()

def init_db():
    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password TEXT NOT NULL,
        rol VARCHAR(50) NOT NULL
    )""")
    
    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS bodegas (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(100) UNIQUE NOT NULL
    )""")
    
    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS proveedores (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(150) UNIQUE NOT NULL,
        nit VARCHAR(50),
        contacto TEXT,
        telefono VARCHAR(50),
        email VARCHAR(100)
    )""")

    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS clientes (
        id SERIAL PRIMARY KEY,
        razon_social VARCHAR(150) UNIQUE NOT NULL,
        identificacion VARCHAR(50) UNIQUE NOT NULL,
        contacto TEXT,
        telefono VARCHAR(50),
        email VARCHAR(100)
    )""")
    
    ejecutar_sql_seguro("""
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
    
    ejecutar_sql_seguro("""
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

    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS ordenes_compra (
        id SERIAL PRIMARY KEY,
        numero_oc VARCHAR(100) UNIQUE NOT NULL,
        proveedor TEXT NOT NULL,
        estado VARCHAR(50) DEFAULT 'ABIERTA',
        fecha_creacion TEXT NOT NULL
    )""")

    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS ordenes_compra_items (
        id SERIAL PRIMARY KEY,
        oc_id INTEGER NOT NULL REFERENCES ordenes_compra(id),
        producto_id INTEGER NOT NULL REFERENCES productos(id),
        cantidad_solicitada NUMERIC NOT NULL,
        cantidad_recibida NUMERIC DEFAULT 0.0,
        costo_pactado NUMERIC NOT NULL,
        moneda VARCHAR(10) DEFAULT 'COP',
        trm NUMERIC DEFAULT 1.0,
        subtotal NUMERIC DEFAULT 0.0,
        monto_iva NUMERIC DEFAULT 0.0,
        costo_total NUMERIC DEFAULT 0.0
    )""")

    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS pedidos_venta (
        id SERIAL PRIMARY KEY,
        numero_pedido VARCHAR(100) UNIQUE NOT NULL,
        cliente TEXT NOT NULL,
        producto_id INTEGER,
        cantidad_solicitada NUMERIC NOT NULL,
        precio_unitario NUMERIC NOT NULL,
        vendedor TEXT NOT NULL,
        fecha_pedido TEXT NOT NULL,
        estado VARCHAR(50) DEFAULT 'PENDIENTE',
        subtotal NUMERIC DEFAULT 0.0,
        monto_iva NUMERIC DEFAULT 0.0,
        precio_total NUMERIC DEFAULT 0.0
    )""")

    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS kits (
        id SERIAL PRIMARY KEY,
        codigo_kit VARCHAR(100) UNIQUE NOT NULL,
        nombre_kit TEXT NOT NULL,
        precio_venta NUMERIC DEFAULT 0.0
    )""")

    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS kit_componentes (
        id SERIAL PRIMARY KEY,
        kit_id INTEGER NOT NULL REFERENCES kits(id),
        componente_id INTEGER NOT NULL REFERENCES productos(id),
        porcentaje_o_cantidad NUMERIC NOT NULL
    )""")

    ejecutar_sql_seguro("""
    CREATE TABLE IF NOT EXISTS kardex (
        id SERIAL PRIMARY KEY,
        fecha TEXT NOT NULL,
        producto_id INTEGER REFERENCES productos(id),
        bodega_id INTEGER REFERENCES bodegas(id),
        tipo_movimiento VARCHAR(50) NOT NULL,
        cantidad NUMERIC NOT NULL,
        costo_unitario NUMERIC NOT NULL,
        usuario TEXT NOT NULL,
        motivo TEXT,
        lote TEXT,
        documento_ref TEXT
    )""")

    ejecutar_sql_seguro("ALTER TABLE productos ADD COLUMN IF NOT EXISTS aplica_iva VARCHAR(2) DEFAULT 'SI';")
    ejecutar_sql_seguro("ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS subtotal NUMERIC DEFAULT 0.0;")
    ejecutar_sql_seguro("ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS monto_iva NUMERIC DEFAULT 0.0;")
    ejecutar_sql_seguro("ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS costo_total NUMERIC DEFAULT 0.0;")
    ejecutar_sql_seguro("ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS cantidad_recibida NUMERIC DEFAULT 0.0;")

    default_users = [
        ("admin", make_hashes("admin123"), "Administrador"),
        ("bodega", make_hashes("bodega123"), "Bodega"),
        ("comercial", make_hashes("comercial123"), "Comercial")
    ]
    for user, pwd, role in default_users:
        ejecutar_sql_seguro("INSERT INTO usuarios (username, password, rol) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING", (user, pwd, role))

    bodegas = ["FINE", "INDUSTRIAL", "MATERIAS PRIMAS", "ENVASES Y DEMÁS"]
    for b in bodegas:
        ejecutar_sql_seguro("INSERT INTO bodegas (nombre) VALUES (%s) ON CONFLICT (nombre) DO NOTHING", (b,))

if 'db_initialized' not in st.session_state:
    init_db()
    st.session_state['db_initialized'] = True

# ==========================================
# LÓGICA DE NEGOCIO Y AUTENTICACIÓN
# ==========================================
def login_user(username, password):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM usuarios WHERE username = %s AND password = %s', (username, make_hashes(password)))
        user = c.fetchone()
        return user
    except Exception as e:
        conn.rollback()
        st.error(f"Error al iniciar sesión: {e}")
        return None
    finally:
        c.close()

def update_password(username, new_password):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('UPDATE usuarios SET password = %s WHERE username = %s', (make_hashes(new_password), username))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        c.close()

def calcular_costo_promedio_movil(existencia_actual, costo_prom_actual, cant_nueva, costo_nuevo_cop):
    if existencia_actual <= 0:
        return costo_nuevo_cop
    return ((existencia_actual * costo_prom_actual) + (cant_nueva * costo_nuevo_cop)) / (existencia_actual + cant_nueva)

@st.cache_data(ttl=5)
def obtener_existencia_producto(producto_id):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT SUM(cantidad_actual) as total FROM lotes WHERE producto_id = %s", (producto_id,))
        res = c.fetchone()['total']
        return float(res) if res else 0.0
    except Exception:
        conn.rollback()
        return 0.0
    finally:
        c.close()

@st.cache_data(ttl=5)
def obtener_oc_pendientes(producto_id):
    """Calcula dinámicamente la cantidad pendiente por recibir de O.C. abiertas o parciales."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT SUM(i.cantidad_solicitada - COALESCE(i.cantidad_recibida, 0)) as oc_cant 
            FROM ordenes_compra_items i 
            JOIN ordenes_compra oc ON i.oc_id = oc.id 
            WHERE i.producto_id = %s 
              AND oc.estado IN ('ABIERTA', 'PARCIAL')
              AND (i.cantidad_solicitada - COALESCE(i.cantidad_recibida, 0)) > 0
        """, (producto_id,))
        res = c.fetchone()['oc_cant']
        return max(0.0, float(res)) if res else 0.0
    except Exception:
        conn.rollback()
        return 0.0
    finally:
        c.close()

def registrar_recepcion(producto_id, cantidad, lote_prov, fab_date, exp_date, costo_cop_base, moneda, trm, costo_ext, remision, obs, usuario, oc_id=None, item_id=None, estado_oc_final='RECIBIDA'):
    conn = get_connection()
    c = conn.cursor()
    try:
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
        
        if item_id:
            c.execute("""
                UPDATE ordenes_compra_items 
                SET cantidad_recibida = COALESCE(cantidad_recibida, 0) + %s 
                WHERE id = %s
            """, (cantidad, item_id))

        if oc_id:
            c.execute("UPDATE ordenes_compra SET estado = %s WHERE id = %s", (estado_oc_final, oc_id))
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        c.close()
    st.cache_data.clear()

def registrar_pedido_venta(num_ped, cliente, kit_id, cantidad, precio, vendedor, subtotal, monto_iva, total):
    conn = get_connection()
    c = conn.cursor()
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.execute("""
            INSERT INTO pedidos_venta (numero_pedido, cliente, producto_id, cantidad_solicitada, precio_unitario, vendedor, fecha_pedido, estado, subtotal, monto_iva, precio_total)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDIENTE', %s, %s, %s)
        """, (num_ped, cliente, kit_id, cantidad, precio, vendedor, fecha_hoy, subtotal, monto_iva, total))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        c.close()
    st.cache_data.clear()

def despachar_pedido_venta(pedido_id, usuario_despacha):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM pedidos_venta WHERE id = %s", (pedido_id,))
        ped = c.fetchone()
        if not ped or ped['estado'] != 'PENDIENTE':
            return False, "El pedido ya fue procesado o no existe."
        
        c.execute("UPDATE pedidos_venta SET estado = 'DESPACHADO' WHERE id = %s", (pedido_id,))
        conn.commit()
        return True, "Despacho realizado con éxito."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        c.close()
        st.cache_data.clear()

def generar_pdf_orden_compra(num_oc, proveedor, items_df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#000080'), spaceAfter=10
    )
    
    story.append(Paragraph("<b>ORDEN DE COMPRA OFICIAL</b>", title_style))
    story.append(Paragraph(f"<b>N° Orden:</b> {num_oc}", styles['Normal']))
    story.append(Paragraph(f"<b>Proveedor:</b> {proveedor}", styles['Normal']))
    story.append(Paragraph(f"<b>Fecha Emisión:</b> {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
    story.append(Spacer(1, 15))
    
    data = [["Cód. Proveedor", "Descripción Proveedor", "Cant.", "Moneda", "P. Unitario", "Subtotal", "IVA", "Total"]]
    subtotal_gral, iva_gral, total_gral = 0.0, 0.0, 0.0
    
    for idx, row in items_df.iterrows():
        sub, iva, tot = float(row['subtotal']), float(row['monto_iva']), float(row['costo_total'])
        subtotal_gral += sub
        iva_gral += iva
        total_gral += tot
        
        data.append([
            str(row['codigo_proveedor']), str(row['nombre_proveedor']), f"{float(row['cantidad_solicitada']):,.2f}",
            str(row['moneda']), f"${float(row['costo_pactado']):,.2f}", f"${sub:,.2f}", f"${iva:,.2f}", f"${tot:,.2f}"
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

@st.cache_data(ttl=5)
def cargar_tabla_sql(query, params=None):
    conn = get_connection()
    try:
        return pd.read_sql_query(query, conn, params=params)
    except Exception:
        conn.rollback()
        return pd.DataFrame()

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

    menu = st.sidebar.radio(
        "Navegación Módulos",
        [
            "📊 Ficha de Producto",
            "👤 Directorio de Clientes",
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

    rol = st.session_state['rol']

    @st.cache_data(ttl=5)
    def obtener_notificacion_pedidos():
        q_pend = """
            SELECT p.numero_pedido, p.cliente, k.nombre_kit, p.cantidad_solicitada, p.vendedor 
            FROM pedidos_venta p 
            LEFT JOIN kits k ON p.producto_id = k.id 
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
        df_prods = cargar_tabla_sql(query)
        
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
                
                conn = get_connection()
                c = conn.cursor()
                tot_entradas = 0.0
                tot_salidas = 0.0
                try:
                    c.execute("SELECT SUM(cantidad) as ent FROM kardex WHERE producto_id = %s AND tipo_movimiento = 'ENTRADA'", (prod_sel_id,))
                    r_ent = c.fetchone()['ent']
                    tot_entradas = float(r_ent) if r_ent else 0.0
                    
                    c.execute("SELECT SUM(cantidad) as sal FROM kardex WHERE producto_id = %s AND tipo_movimiento IN ('SALIDA', 'ENSAMBLE', 'MERMA')", (prod_sel_id,))
                    r_sal = c.fetchone()['sal']
                    tot_salidas = float(r_sal) if r_sal else 0.0
                except Exception:
                    conn.rollback()
                finally:
                    c.close()

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
                df_lotes = cargar_tabla_sql("SELECT lote_proveedor, cantidad_actual, fecha_fabricacion, fecha_vencimiento, costo_unitario, remision_factura, observaciones FROM lotes WHERE producto_id = %s AND cantidad_actual > 0", params=(prod_sel_id,))
                st.dataframe(df_lotes, use_container_width=True)
            else:
                st.info("👆 Por favor seleccione un producto del desplegable arriba para visualizar su ficha técnica e inventarios.")
        else:
            st.warning("⚠️ No se encontraron productos registrados.")

    elif menu == "👤 Directorio de Clientes":
        st.title("👤 Gestión y Registro de Clientes")
        
        with st.expander("➕ Registrar Nuevo Cliente", expanded=True):
            with st.form("form_crear_cliente", clear_on_submit=True):
                c_cl1, c_cl2 = st.columns(2)
                razon_social = c_cl1.text_input("Nombre o Razón Social:")
                identificacion = c_cl2.text_input("Cédula o NIT:")
                
                c_cl3, c_cl4, c_cl5 = st.columns(3)
                contacto = c_cl3.text_input("Contacto:")
                telefono = c_cl4.text_input("Teléfono:")
                email = c_cl5.text_input("Email:")
                
                if st.form_submit_button("Guardar Cliente"):
                    if not razon_social or not identificacion:
                        st.error("❌ Los campos Razón Social e Identificación (NIT/Cédula) son obligatorios.")
                    else:
                        try:
                            conn = get_connection()
                            c = conn.cursor()
                            c.execute("""
                                INSERT INTO clientes (razon_social, identificacion, contacto, telefono, email)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (razon_social, identificacion, contacto, telefono, email))
                            conn.commit()
                            c.close()
                            st.success(f"✅ Cliente '{razon_social}' registrado con éxito.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al registrar cliente: {e}")

        st.subheader("Listado de Clientes Registrados")
        df_clientes = cargar_tabla_sql("SELECT razon_social, identificacion, contacto, telefono, email FROM clientes ORDER BY razon_social ASC")
        if not df_clientes.empty:
            st.dataframe(df_clientes, use_container_width=True)
        else:
            st.info("Aún no hay clientes registrados.")

    elif menu == "🛒 Pedidos y Cotizaciones":
        st.title("🛒 Módulo de Pedidos de Venta, Cotizaciones y Despachos")
        sub_vta = st.radio("Acción a realizar:", ["➕ Montar Nuevo Pedido / Cotización", "🚚 Control de Despachos y Facturación"], horizontal=True)
        
        if sub_vta == "➕ Montar Nuevo Pedido / Cotización":
            st.subheader("Registrar Orden de Pedido Comercial / Cotización")
            if rol not in ["Administrador", "Comercial"]:
                st.warning("⚠️ Perfil sin autorización para montar pedidos de venta.")
            else:
                df_cli = cargar_tabla_sql("SELECT id, razon_social, identificacion FROM clientes ORDER BY razon_social ASC")
                df_kits_vta = cargar_tabla_sql("SELECT id, codigo_kit, nombre_kit, precio_venta FROM kits ORDER BY nombre_kit ASC")
                
                if df_cli.empty:
                    st.warning("⚠️ Debe registrar al menos un cliente en el menú '👤 Directorio de Clientes' antes de realizar un pedido.")
                elif df_kits_vta.empty:
                    st.warning("⚠️ No hay Kits o Ensambles creados en la base de datos. Vaya al menú '🧪 Kits y Ensambles'.")
                else:
                    with st.form("form_nuevo_pedido", clear_on_submit=True):
                        c_p1, c_p2 = st.columns(2)
                        num_ped = c_p1.text_input("Número / Código de Pedido (ej: PED-001):")
                        
                        cliente_sel_id = c_p2.selectbox(
                            "Buscar / Seleccionar Cliente (Escriba Inicial, Nombre o NIT):",
                            df_cli['id'].tolist(),
                            format_func=lambda x: f"{df_cli[df_cli['id']==x]['razon_social'].values[0]} | NIT/CC: {df_cli[df_cli['id']==x]['identificacion'].values[0]}"
                        )
                        
                        cli_info = df_cli[df_cli['id'] == cliente_sel_id].iloc[0]
                        st.text_input("Identificación Cliente (Sincronizado Aut.):", value=cli_info['identificacion'], disabled=True)

                        kit_ped_id = st.selectbox(
                            "Producto / Ensamble a Vender (Búsqueda por Nombre o Código Kit):",
                            df_kits_vta['id'].tolist(),
                            format_func=lambda x: f"{df_kits_vta[df_kits_vta['id']==x]['codigo_kit'].values[0]} - {df_kits_vta[df_kits_vta['id']==x]['nombre_kit'].values[0]}"
                        )
                        
                        k_sel_info = df_kits_vta[df_kits_vta['id'] == kit_ped_id].iloc[0]
                        
                        c_p3, c_p4 = st.columns(2)
                        cant_ped = c_p3.number_input("Cantidad Requerida (KG/Unidades):", min_value=0.1, value=10.0)
                        precio_ped_base = c_p4.number_input("Precio Base Unitario ($ COP sin IVA):", value=float(k_sel_info['precio_venta']) if k_sel_info['precio_venta'] else 0.0)
                        
                        subtotal = cant_ped * precio_ped_base
                        monto_iva = subtotal * 0.19
                        total_pedido = subtotal + monto_iva
                        
                        st.markdown(f"""
                        * **Subtotal Base:** ${subtotal:,.2f} COP
                        * **IVA Calculado (19%):** ${monto_iva:,.2f} COP
                        * **TOTAL PEDIDO / COTIZACIÓN:** `${total_pedido:,.2f} COP`
                        """)
                        
                        if st.form_submit_button("Guardar y Registrar Pedido"):
                            if not num_ped:
                                st.error("❌ Indique el número de pedido.")
                            else:
                                try:
                                    registrar_pedido_venta(
                                        num_ped, cli_info['razon_social'], kit_ped_id, cant_ped, 
                                        precio_ped_base, st.session_state['username'], subtotal, monto_iva, total_pedido
                                    )
                                    st.success(f"✅ Pedido {num_ped} para {cli_info['razon_social']} registrado exitosamente.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al registrar pedido: {e}")

        elif sub_vta == "🚚 Control de Despachos y Facturación":
            st.subheader("Despacho e Impacto en Inventario / Kardex")
            df_pedidos = cargar_tabla_sql("""
                SELECT p.id, p.numero_pedido, p.cliente, k.codigo_kit, k.nombre_kit, p.cantidad_solicitada, p.precio_unitario, p.subtotal, p.monto_iva, p.precio_total, p.vendedor, p.fecha_pedido, p.estado
                FROM pedidos_venta p
                LEFT JOIN kits k ON p.producto_id = k.id
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
                    ped_to_desp = st.selectbox("Seleccionar Pedido Pendiente por Despachar:", pedidos_pendientes['id'].tolist(), format_func=lambda x: f"Pedido {pedidos_pendientes[pedidos_pendientes['id']==x]['numero_pedido'].values[0]} - Cliente: {pedidos_pendientes[pedidos_pendientes['id']==x]['cliente'].values[0]}")
                    
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

    elif menu == "📦 Maestro de Productos y Lotes":
        st.title("📦 Crear y Administrar Productos")
        
        if rol != "Administrador":
            st.warning("⚠️ Rol limitado: La creación y modificación de productos es función exclusiva del rol **Administrador**.")
        else:
            df_provs_db = cargar_tabla_sql("SELECT nombre FROM proveedores ORDER BY nombre ASC")
            lista_proveedores = df_provs_db['nombre'].tolist() if not df_provs_db.empty else []

            with st.form("crear_producto", clear_on_submit=True):
                st.subheader("Formulario de Creación de Producto AURANZA")
                c1, c2, c3 = st.columns(3)
                codigo_au = c1.text_input("Código AU Interno (ej: AUH0001):")
                codigo_prov = c2.text_input("Código Proveedor (ej: XB0102):")
                nombre_au = c3.text_input("Nombre AU (ej: BAMBU):")
                
                c4, c5, c6 = st.columns(3)
                nombre_prov = c4.text_input("Nombre en Proveedor (ej: BAMBOO):")
                
                if lista_proveedores:
                    proveedor = c5.selectbox("Nombre del Proveedor:", lista_proveedores)
                else:
                    proveedor = c5.selectbox("Nombre del Proveedor:", ["-- No hay proveedores creados --"])

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
                            conn = get_connection()
                            c = conn.cursor()
                            c.execute("""
                                INSERT INTO productos (codigo_au, codigo_proveedor, nombre_au, nombre_proveedor, proveedor, categoria, linea, bodega_id, precio_venta, punto_pedido, nivel_minimo, nivel_maximo, aplica_iva)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (codigo_au, codigo_prov, nombre_au, nombre_prov, proveedor, categoria, linea, bodega_id, precio_vta, pt_pedido, nv_min, nv_max, aplica_iva))
                            conn.commit()
                            c.close()
                            st.success(f"✅ Producto {codigo_au} - {nombre_au} creado exitosamente con IVA: {aplica_iva}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al crear producto: {e}")

        st.subheader("Inventario Consolidado por Productos")
        df_prods_all = cargar_tabla_sql("SELECT p.codigo_au, p.codigo_proveedor, p.nombre_au, p.proveedor, b.nombre as bodega, p.costo_promedio, p.ultimo_costo, p.precio_venta, p.aplica_iva FROM productos p JOIN bodegas b ON p.bodega_id = b.id")
        if not df_prods_all.empty:
            st.dataframe(df_prods_all, use_container_width=True)
        else:
            st.info("Aún no hay productos registrados.")

    elif menu == "🏢 Directorio de Proveedores":
        st.title("🏢 Gestión y Directorio de Proveedores")
        
        if rol == "Administrador":
            with st.expander("➕ Registrar Nuevo Proveedor"):
                with st.form("form_proveedor", clear_on_submit=True):
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
                                conn = get_connection()
                                c = conn.cursor()
                                c.execute("INSERT INTO proveedores (nombre, nit, contacto, telefono, email) VALUES (%s, %s, %s, %s, %s)", (nom_prov, nit_prov, contacto_prov, tel_prov, email_prov))
                                conn.commit()
                                c.close()
                                st.success(f"✅ Proveedor {nom_prov} registrado correctamente.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al guardar proveedor: {e}")

        st.subheader("Listado de Proveedores Registrados")
        df_provs = cargar_tabla_sql("SELECT nombre, nit, contacto, telefono, email FROM proveedores")
        if not df_provs.empty:
            st.dataframe(df_provs, use_container_width=True)
        else:
            st.info("Aún no hay proveedores registrados.")

    elif menu == "🧾 Órdenes de Compra y Recepción":
        st.title("🧾 Gestión de Compras y Recepciones")
        sub_oc = st.radio("Acción a realizar:", ["Emitir Órden de Compra (OC)", "📦 Recepción de Mercancía en Bodega"], horizontal=True)

        if sub_oc == "Emitir Órden de Compra (OC)":
            st.subheader("Generar Nueva Orden de Compra")
            if rol not in ["Administrador"]:
                st.warning("⚠️ Emisión de Compras restringida a perfil Administrador.")
            else:
                if "oc_key_version" not in st.session_state:
                    st.session_state["oc_key_version"] = 0

                if "msg_exito_oc" in st.session_state:
                    st.success(st.session_state["msg_exito_oc"])
                    del st.session_state["msg_exito_oc"]

                df_prods = cargar_tabla_sql("SELECT id, codigo_au, codigo_proveedor, nombre_au, nombre_proveedor, proveedor, aplica_iva FROM productos")
                
                if df_prods.empty:
                    st.warning("⚠️ Primero cree productos en el menú 'Maestro de Productos y Lotes'.")
                else:
                    try:
                        df_count = cargar_tabla_sql("SELECT COUNT(*) as total FROM ordenes_compra")
                        next_id = int(df_count['total'].values[0]) + 1 if not df_count.empty else 1
                    except Exception:
                        next_id = 1
                    
                    sugerido_oc = f"OC-{next_id:04d}"

                    num_oc = st.text_input("Número de OC (Generado automáticamente):", value=sugerido_oc, key=f"num_oc_{st.session_state['oc_key_version']}")
                    
                    prod_oc_id = st.selectbox(
                        "Seleccionar Producto:", 
                        options=df_prods['id'].tolist(), 
                        index=None,
                        placeholder="-- Seleccione un producto de la lista --",
                        format_func=lambda x: f"{df_prods[df_prods['id']==x]['nombre_au'].values[0]} | Proveedor: {df_prods[df_prods['id']==x]['proveedor'].values[0]}",
                        key=f"prod_oc_id_{st.session_state['oc_key_version']}"
                    )
                    
                    if prod_oc_id is not None:
                        prod_info = df_prods[df_prods['id']==prod_oc_id].iloc[0]
                        
                        st.info(f"🏢 **Proveedor Asignado:** `{prod_info['proveedor']}` | **Cód. Proveedor:** `{prod_info['codigo_proveedor']}` | **Nombre en Prov:** `{prod_info['nombre_proveedor']}`")
                        
                        col_a, col_b, col_c = st.columns(3)
                        cant_oc = col_a.number_input("Cantidad a Solicitar (KG/Unidades):", min_value=0.0, value=0.0, step=1.0, key=f"cant_oc_{st.session_state['oc_key_version']}")
                        moneda_oc = col_b.selectbox("Moneda O.C.:", ["COP", "USD", "EUR"], key=f"moneda_oc_{st.session_state['oc_key_version']}")
                        trm_oc = col_c.number_input("TRM Proyectada (COP):", min_value=1.0, value=1.0 if moneda_oc == "COP" else 4100.0, key=f"trm_oc_{st.session_state['oc_key_version']}")
                        
                        costo_unit_ext = st.number_input(f"Costo Base Unitario sin IVA en {moneda_oc}:", min_value=0.0, value=0.0, step=100.0, key=f"costo_unit_ext_{st.session_state['oc_key_version']}")
                        
                        costo_cop_base = costo_unit_ext * trm_oc if moneda_oc != "COP" else costo_unit_ext
                        subtotal = cant_oc * costo_cop_base
                        aplica_v = prod_info.get('aplica_iva', 'SI')
                        monto_iva = subtotal * 0.19 if aplica_v == 'SI' else 0.0
                        costo_total = subtotal + monto_iva
                        
                        st.markdown("### 💰 Desglose Financiero O.C.")
                        st.markdown(f"* **Subtotal Base Costo:** ${subtotal:,.2f} COP")
                        st.markdown(f"* **Monto Impuesto IVA (19%):** ${monto_iva:,.2f} COP")
                        st.markdown(f"* **COSTO TOTAL FACTURA PROVEEDOR:** `${costo_total:,.2f} COP`")

                        if st.button("Emitir Orden de Compra y Generar PDF"):
                            if not num_oc:
                                st.error("❌ El número de Orden de Compra no puede estar vacío.")
                            elif cant_oc <= 0:
                                st.error("❌ La cantidad a solicitar debe ser mayor al valor actual.")
                            elif costo_unit_ext <= 0:
                                st.error("❌ El costo unitario debe ser mayor al valor actual.")
                            else:
                                try:
                                    conn = get_connection()
                                    c = conn.cursor()
                                    c.execute(
                                        "INSERT INTO ordenes_compra (numero_oc, proveedor, fecha_creacion) VALUES (%s, %s, %s) RETURNING id", 
                                        (num_oc, prod_info['proveedor'], datetime.now().strftime("%Y-%m-%d"))
                                    )
                                    oc_id = c.fetchone()['id']
                                    
                                    c.execute("""
                                        INSERT INTO ordenes_compra_items 
                                        (oc_id, producto_id, cantidad_solicitada, cantidad_recibida, costo_pactado, moneda, trm, subtotal, monto_iva, costo_total)
                                        VALUES (%s, %s, %s, 0.0, %s, %s, %s, %s, %s, %s)
                                    """, (oc_id, prod_oc_id, cant_oc, costo_cop_base, moneda_oc, trm_oc, subtotal, monto_iva, costo_total))
                                    
                                    conn.commit()
                                    c.close()
                                    
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
                                    st.session_state["msg_exito_oc"] = f"✅ Orden de Compra {num_oc} emitida exitosamente."
                                    st.download_button("📄 Descargar Documento PDF", data=pdf_bytes, file_name=f"OC_{num_oc}.pdf", mime="application/pdf")
                                    
                                    st.session_state["oc_key_version"] += 1
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"❌ Error al guardar en base de datos: {ex}")
                    else:
                        st.info("💡 Por favor, seleccione un producto para ingresar las cantidades y costos.")

        elif sub_oc == "📦 Recepción de Mercancía en Bodega":
            st.subheader("Entrada de Mercancía a Bodega (Recepción)")
            if rol not in ["Administrador", "Bodega"]:
                st.warning("⚠️ Módulo de recepción reservado para perfiles Bodega o Administrador.")
            else:
                if 'msg_exito_recepcion' in st.session_state:
                    st.success(st.session_state['msg_exito_recepcion'])
                    del st.session_state['msg_exito_recepcion']

                df_ocs = cargar_tabla_sql("""
                    SELECT oc.id as oc_id, oc.numero_oc, oc.proveedor, i.id as item_id, i.producto_id, 
                           i.cantidad_solicitada, COALESCE(i.cantidad_recibida, 0) as cantidad_recibida,
                           (i.cantidad_solicitada - COALESCE(i.cantidad_recibida, 0)) as saldo_pendiente,
                           i.costo_pactado, i.moneda, i.trm, i.subtotal, i.monto_iva, i.costo_total, p.aplica_iva
                    FROM ordenes_compra oc 
                    JOIN ordenes_compra_items i ON oc.id = i.oc_id 
                    JOIN productos p ON i.producto_id = p.id
                    WHERE oc.estado IN ('ABIERTA', 'PARCIAL')
                      AND (i.cantidad_solicitada - COALESCE(i.cantidad_recibida, 0)) > 0
                """)
                
                if df_ocs.empty:
                    st.info("No hay Órdenes de Compra abiertas o parciales pendientes por recibir.")
                else:
                    opciones_oc = [None] + df_ocs['oc_id'].tolist()
                    
                    oc_sel = st.selectbox(
                        "Seleccionar OC por Recibir:", 
                        opciones_oc, 
                        index=0,
                        placeholder="-- Seleccionar Orden de Compra --",
                        format_func=lambda x: "-- Seleccionar Orden de Compra --" if x is None else f"OC: {df_ocs[df_ocs['oc_id']==x]['numero_oc'].values[0]} - Prov: {df_ocs[df_ocs['oc_id']==x]['proveedor'].values[0]} (Pendiente: {df_ocs[df_ocs['oc_id']==x]['saldo_pendiente'].values[0]:,.2f} KG)"
                    )
                    
                    if oc_sel is None:
                        st.info("👈 Por favor seleccione una Orden de Compra para desplegar la información y procesar la entrada.")
                    else:
                        item_oc = df_ocs[df_ocs['oc_id']==oc_sel].iloc[0]
                        oc_id_curr = str(item_oc['oc_id'])
                        
                        saldo_pen = float(item_oc['saldo_pendiente'])
                        cant_sol_orig = float(item_oc['cantidad_solicitada'])
                        cant_rec_acum = float(item_oc['cantidad_recibida'])
                        
                        st.write(f"Recibiendo producto ID: **{item_oc['producto_id']}** | Solicitado: **{cant_sol_orig:.2f} KG** | Ya Recibido: **{cant_rec_acum:.2f} KG** | **Saldo Pendiente OC: {saldo_pen:.2f} KG**")
                        
                        st.markdown("---")
                        
                        c_rx1, c_rx2 = st.columns(2)
                        cant_rx = c_rx1.number_input(
                            "Cantidad Real Recibida (KG):", 
                            min_value=0.01, 
                            max_value=saldo_pen, 
                            value=saldo_pen, 
                            step=1.0, 
                            key=f"cant_rx_{oc_id_curr}"
                        )
                        remision = c_rx2.text_input(
                            "Documento / Remisión / Factura Proveedor:", 
                            key=f"remision_{oc_id_curr}"
                        )
                        
                        estado_oc_final = "RECIBIDA"
                        if cant_rx < saldo_pen:
                            remanente = saldo_pen - cant_rx
                            st.warning(f"⚠️ Entrega parcial detectada: Quedarán **{remanente:.2f} KG** pendientes de este pedido.")
                            opcion_cierre = st.radio(
                                "¿Cómo desea manejar el estado de la Orden de Compra?",
                                ["Mantener OC Abierta (Parcial)", "Cerrar / Dar por Cumplida la OC"],
                                index=0,
                                key=f"opcion_cierre_{oc_id_curr}"
                            )
                            estado_oc_final = "PARCIAL" if opcion_cierre == "Mantener OC Abierta (Parcial)" else "RECIBIDA"

                        st.markdown("### 💰 Casillas de Validación Cruzada de Facturación")
                        cm1, cm2 = st.columns(2)
                        
                        index_moneda = ["COP", "USD", "EUR"].index(item_oc['moneda']) if item_oc['moneda'] in ["COP", "USD", "EUR"] else 0
                        moneda_rx = cm1.selectbox(
                            "Moneda Factura:", 
                            ["COP", "USD", "EUR"], 
                            index=index_moneda, 
                            key=f"moneda_rx_{oc_id_curr}"
                        )
                        trm_rx = cm2.number_input(
                            "TRM Aplicada Factura:", 
                            value=float(item_oc['trm']), 
                            key=f"trm_rx_{oc_id_curr}"
                        )
                        
                        costo_pactado_oc = float(item_oc['costo_pactado'])
                        costo_unitario_factura = st.number_input(
                            f"Costo Unitario Facturado sin IVA ({moneda_rx}/KG):", 
                            min_value=0.0, 
                            value=costo_pactado_oc, 
                            step=10.0,
                            key=f"costo_factura_{oc_id_curr}"
                        )
                        
                        # RECÁLCULO REACTIVO COMPLETO
                        costo_cop_base_unit = costo_unitario_factura * trm_rx if moneda_rx != "COP" else costo_unitario_factura
                        rx_subtotal = cant_rx * costo_cop_base_unit
                        
                        aplica_v = item_oc.get('aplica_iva', 'SI')
                        rx_iva = rx_subtotal * 0.19 if aplica_v == 'SI' else 0.0
                        rx_total = rx_subtotal + rx_iva

                        c_sub, c_iva = st.columns(2)
                        
                        # KEYS REACTIVAS CON VALORES INTERNOS (EVITA TRABAR EL ESTADO DE STREAMLIT)
                        dynamic_sub_key = f"dyn_sub_{oc_id_curr}_{cant_rx}_{costo_unitario_factura}_{moneda_rx}_{trm_rx}"
                        dynamic_iva_key = f"dyn_iva_{oc_id_curr}_{cant_rx}_{costo_unitario_factura}_{moneda_rx}_{trm_rx}"

                        c_sub.text_input("Subtotal Costo Facturado ($ Calculado):", value=f"${rx_subtotal:,.2f}", disabled=True, key=dynamic_sub_key)
                        c_iva.text_input("Monto IVA Facturado ($ Calculado):", value=f"${rx_iva:,.2f}", disabled=True, key=dynamic_iva_key)
                        
                        st.markdown(f"### **TOTAL FACTURA PROVEEDOR:** `${rx_total:,.2f} COP`")
                        st.info(f"💡 **Costo Base Unitario de Entrada a Valoración (sin IVA):** ${costo_cop_base_unit:,.2f} COP / KG")
                        
                        if costo_pactado_oc > 0:
                            variacion = ((costo_cop_base_unit - costo_pactado_oc) / costo_pactado_oc) * 100.0
                            if abs(variacion) > 0.01:
                                if variacion > 0:
                                    st.warning(f"🚨 **ALERTA DE DESVIACIÓN DE PRECIO:** El costo unitario de entrada subió un **{variacion:.2f}%** respecto al costo pactado en la OC (${costo_pactado_oc:,.2f} COP/KG).")
                                else:
                                    st.info(f"ℹ️ **ALERTA DE DESVIACIÓN DE PRECIO:** El costo unitario de entrada bajó un **{abs(variacion):.2f}%** respecto al costo pactado en la OC (${costo_pactado_oc:,.2f} COP/KG).")

                        st.markdown("---")
                        st.markdown("### 📋 Información Técnica y Control de Lote")
                        
                        lote_prov = st.text_input("Número de Lote del Proveedor:", key=f"lote_prov_{oc_id_curr}")
                        
                        cd1, cd2 = st.columns(2)
                        fab_date = cd1.date_input("Fecha de Fabricación:", value=None, key=f"fab_date_{oc_id_curr}")
                        exp_date = cd2.date_input("Fecha de Vencimiento:", value=None, key=f"exp_date_{oc_id_curr}")
                        
                        obs_rx = st.text_area("Observaciones de Recepción:", key=f"obs_rx_{oc_id_curr}")
                        
                        if st.button("🚀 Confirmar Entrada y Actualizar Costo Promedio Móvil", key=f"btn_confirmar_{oc_id_curr}"):
                            if not lote_prov.strip():
                                st.error("❌ Por favor ingrese el número de lote del proveedor.")
                            elif not fab_date or not exp_date:
                                st.error("❌ Por favor seleccione tanto la fecha de fabricación como la de vencimiento.")
                            elif costo_unitario_factura <= 0:
                                st.error("❌ El costo unitario facturado debe ser mayor a 0.")
                            else:
                                registrar_recepcion(
                                    int(item_oc['producto_id']), 
                                    cant_rx, 
                                    lote_prov.strip(), 
                                    str(fab_date), 
                                    str(exp_date), 
                                    costo_cop_base_unit, 
                                    moneda_rx, 
                                    trm_rx, 
                                    costo_unitario_factura, 
                                    remision, 
                                    obs_rx, 
                                    st.session_state['username'], 
                                    oc_id=int(item_oc['oc_id']),
                                    item_id=int(item_oc['item_id']),
                                    estado_oc_final=estado_oc_final
                                )
                                st.session_state['msg_exito_recepcion'] = f"✅ ¡Mercancía ingresada con éxito! Lote: {lote_prov.strip()} - Cantidad: {cant_rx} KG."
                                st.toast("✅ Mercancía ingresada con éxito al sistema.", icon="🎉")
                                st.rerun()

    elif menu == "🧪 Kits y Ensambles":
        st.title("🧪 Creación y Ensamble de Kits")
        st.subheader("Fórmulas de Ensamble y Costo Teórico Actualizado")
        
        df_prods = cargar_tabla_sql("SELECT id, codigo_au, nombre_au, costo_promedio FROM productos")
        
        if df_prods.empty:
            st.warning("⚠️ Debe registrar productos en 'Maestro de Productos y Lotes' para armar fórmulas.")
        else:
            if rol == "Administrador":
                with st.expander("➕ Crear / Configurar Fórmula de Kit", expanded=True):
                    c_num = st.number_input("Código del Kit / Producto Final:", value="", placeholder="Ingrese los números (ej. 850001)")
                    cod_kit = f"AU{c_num.strip()}"
                    
                    if c_num.strip():
                        st.caption(f"Código resultante: **{cod_kit}**")
                        
                    nom_kit = st.text_input("Nombre Comercial Kit:")
                    
                    st.write("Seleccione Componentes Químicos (Base para 1 KG):")

                    prod_map = {row['id']: f"{row['codigo_au']} - {row['nombre_au']}" for _, row in df_prods.iterrows()}
                    costo_map = {row['id']: float(row['costo_promedio']) if row['costo_promedio'] else 0.0 for _, row in df_prods.iterrows()}
                    todos_los_ids = list(prod_map.keys())

                    ids_comp1 = [p_id for p_id in todos_los_ids if p_id not in [st.session_state.get('c2'), st.session_state.get('c3')]]
                    comp1 = st.selectbox(
                        "Componente 1:", 
                        options=ids_comp1, 
                        index=None, 
                        placeholder="Escriba o seleccione un componente...", 
                        format_func=lambda x: prod_map[x],
                        key='c1'
                    )
                    prop1 = st.number_input("Cantidad Componente 1 (KG):", min_value=0.0, value=0.0, step=0.01)
                    
                    ids_comp2 = [p_id for p_id in todos_los_ids if p_id not in [st.session_state.get('c1'), st.session_state.get('c3')]]
                    comp2 = st.selectbox(
                        "Componente 2:", 
                        options=ids_comp2, 
                        index=None, 
                        placeholder="Escriba o seleccione un componente...", 
                        format_func=lambda x: prod_map[x],
                        key='c2'
                    )
                    prop2 = st.number_input("Cantidad Componente 2 (KG):", min_value=0.0, value=0.0, step=0.01)

                    ids_comp3 = [p_id for p_id in todos_los_ids if p_id not in [st.session_state.get('c1'), st.session_state.get('c2')]]
                    comp3 = st.selectbox(
                        "Componente 3:", 
                        options=ids_comp3, 
                        index=None, 
                        placeholder="Escriba o seleccione un componente...", 
                        format_func=lambda x: prod_map[x],
                        key='c3'
                    )
                    prop3 = st.number_input("Cantidad Componente 3 (KG):", min_value=0.0, value=0.0, step=0.01)

                    total_kg = prop1 + prop2 + prop3
                    st.markdown(f"**Sumatoria de componentes:** `{total_kg:.3f} KG` / `1.000 KG`")

                    costo_kit_calc = 0.0
                    if comp1 and prop1 > 0:
                        costo_kit_calc += prop1 * costo_map.get(comp1, 0.0)
                    if comp2 and prop2 > 0:
                        costo_kit_calc += prop2 * costo_map.get(comp2, 0.0)
                    if comp3 and prop3 > 0:
                        costo_kit_calc += prop3 * costo_map.get(comp3, 0.0)

                    st.number_input("Costo del Kit ($ COP):", value=costo_kit_calc, disabled=True, format="%.2f")

                    precio_vta_kit = st.number_input("Precio de Venta ($ COP):", min_value=0.0, value=0.0, step=100.0)

                    if precio_vta_kit > 0:
                        rentabilidad_calc = ((precio_vta_kit - costo_kit_calc) / precio_vta_kit) * 100.0
                    else:
                        rentabilidad_calc = 0.0

                    st.number_input("Rentabilidad (%):", value=rentabilidad_calc, disabled=True, format="%.2f")

                    if st.button("Guardar Fórmula Kit"):
                        if not c_num.strip() or not nom_kit:
                            st.error("❌ Indique el código y nombre del Kit.")
                        elif abs(total_kg - 1.0) > 0.0001:
                            st.error(f"❌ La sumatoria de las cantidades de los componentes debe ser exactamente 1.00 KG. (Suma actual: {total_kg:.3f} KG)")
                        elif not any([comp1, comp2, comp3]):
                            st.error("❌ Seleccione al menos un componente para el kit.")
                        else:
                            try:
                                conn = get_connection()
                                c = conn.cursor()
                                c.execute("INSERT INTO kits (codigo_kit, nombre_kit, precio_venta) VALUES (%s, %s, %s) RETURNING id", (cod_kit, nom_kit, precio_vta_kit))
                                kit_id = c.fetchone()['id']
                                
                                if comp1 and prop1 > 0:
                                    c.execute("INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad) VALUES (%s, %s, %s)", (kit_id, comp1, prop1))
                                if comp2 and prop2 > 0:
                                    c.execute("INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad) VALUES (%s, %s, %s)", (kit_id, comp2, prop2))
                                if comp3 and prop3 > 0:
                                    c.execute("INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad) VALUES (%s, %s, %s)", (kit_id, comp3, prop3))
                                    
                                conn.commit()
                                c.close()
                                st.success("✅ Fórmula de Kit guardada exitosamente.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al guardar fórmula: {e}")

        st.subheader("Análisis de Costo y Margen Teórico por Kit")
        df_kits_list = cargar_tabla_sql("SELECT * FROM kits")
        if not df_kits_list.empty:
            for idx, k_item in df_kits_list.iterrows():
                df_comp_k = cargar_tabla_sql("""
                    SELECT kc.porcentaje_o_cantidad, p.costo_promedio, p.nombre_au
                    FROM kit_componentes kc
                    JOIN productos p ON kc.componente_id = p.id
                    WHERE kc.kit_id = %s
                """, params=(k_item['id'],))
                
                costo_mezcla_kg = sum(df_comp_k['porcentaje_o_cantidad'] * df_comp_k['costo_promedio']) if not df_comp_k.empty else 0.0
                st.info(f"🧪 **{k_item['codigo_kit']} - {k_item['nombre_kit']}** | Costo Promedio Móvil Mezcla: **${costo_mezcla_kg:,.2f} COP / KG** | Precio Venta: **${k_item['precio_venta']:,.2f} COP**")
        else:
            st.info("Aún no hay kits creados.")

    elif menu == "🚨 Requerimiento Comercial (MRP)":
        st.title("🚨 Motor MRP: Análisis de Materias Primas y Empaques")
        df_kits = cargar_tabla_sql("SELECT * FROM kits")

        if df_kits.empty:
            st.warning("⚠️ No existen Kits registrados para simular el MRP. Regístrelos en 'Kits y Ensambles'.")
        else:
            kit_sel = st.selectbox("Seleccionar Kit a Comercializar:", df_kits['id'].tolist(), format_func=lambda x: f"{df_kits[df_kits['id']==x]['codigo_kit'].values[0]} - {df_kits[df_kits['id']==x]['nombre_kit'].values[0]}")
            cant_solicitada = st.number_input("Cantidad Requerida por Cliente (KG):", value=300.0)
            
            if st.button("🔍 Evaluar Disponibilidad y Generar Requerimientos"):
                st.subheader("1. Evaluación de Materias Primas")
                df_comps = cargar_tabla_sql("""
                    SELECT kc.componente_id, p.codigo_au, p.nombre_au, kc.porcentaje_o_cantidad, p.costo_promedio
                    FROM kit_componentes kc
                    JOIN productos p ON kc.componente_id = p.id
                    WHERE kc.kit_id = %s
                """, params=(kit_sel,))
                
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
                
                st.subheader("2. Regla de Empaques y Evaluación en Bodega 4")
                if cant_solicitada <= 2:
                    unidades_envase, tipo_envase = 1, "Envase 2 KG"
                elif cant_solicitada <= 5:
                    unidades_envase, tipo_envase = 1, "Envase 5 KG"
                else:
                    unidades_envase = int(cant_solicitada // 20) + (1 if cant_solicitada % 20 != 0 else 0)
                    tipo_envase = "Envase 20 KG"
                    
                st.warning(f"📦 Requerimiento Logístico: **{unidades_envase} Unidades de {tipo_envase} + {unidades_envase} Tapas + {unidades_envase} Tapones**.")
                st.metric("Costo Estimado Mezcla Materias Primas", f"${costo_mezcla_total:,.2f} COP")

    elif menu == "📜 Kardex e Historial":
        st.title("📜 Trazabilidad Completa / Kardex Auditable")
        df_kardex = cargar_tabla_sql("""
            SELECT k.fecha, p.codigo_au, p.nombre_au, b.nombre as bodega, k.tipo_movimiento, k.cantidad, k.costo_unitario, k.usuario, k.motivo, k.lote, k.documento_ref
            FROM kardex k
            LEFT JOIN productos p ON k.producto_id = p.id
            LEFT JOIN bodegas b ON k.bodega_id = b.id
            ORDER BY k.id DESC
        """)
        if not df_kardex.empty:
            st.dataframe(df_kardex, use_container_width=True)
        else:
            st.info("Aún no hay movimientos registrados en el Kardex.")

    elif menu == "⚙️ Mi Cuenta y Configuración":
        st.title("⚙️ Gestión de Claves y Usuarios")
        
        st.subheader("🔑 Cambiar mi Contraseña")
        with st.form("form_cambiar_clave", clear_on_submit=True):
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
            try:
                conn = get_connection()
                c_usr = conn.cursor()
                c_usr.execute("SELECT id, username, rol FROM usuarios")
                users_list = c_usr.fetchall()
                c_usr.close()
                
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
            except Exception as e:
                st.error(f"Error al cargar usuarios: {e}")
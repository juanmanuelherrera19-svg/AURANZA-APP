import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import hashlib

# ==========================================
# CONFIGURACIÓN E INICIALIZACIÓN DE BD
# ==========================================
st.set_page_config(page_title="AURANZA SAS - ERP/MRP System", layout="wide", page_icon="🧪")

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def get_connection():
    conn = sqlite3.connect("auranza_inventario.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabla de Usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        rol TEXT NOT NULL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bodegas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_au TEXT UNIQUE NOT NULL,
        codigo_proveedor TEXT NOT NULL,
        nombre_au TEXT NOT NULL,
        nombre_proveedor TEXT NOT NULL,
        proveedor TEXT NOT NULL,
        categoria TEXT NOT NULL,
        linea TEXT NOT NULL,
        bodega_id INTEGER NOT NULL,
        unidad_medida TEXT DEFAULT 'KG',
        costo_promedio REAL DEFAULT 0.0,
        ultimo_costo REAL DEFAULT 0.0,
        fecha_ultimo_costo TEXT,
        precio_venta REAL DEFAULT 0.0,
        punto_pedido REAL DEFAULT 0.0,
        nivel_minimo REAL DEFAULT 0.0,
        nivel_maximo REAL DEFAULT 0.0,
        comp_venta REAL DEFAULT 0.0,
        comp_op REAL DEFAULT 0.0,
        comp_requisicion REAL DEFAULT 0.0,
        FOREIGN KEY (bodega_id) REFERENCES bodegas(id)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL,
        bodega_id INTEGER NOT NULL,
        lote_proveedor TEXT NOT NULL,
        fecha_fabricacion TEXT,
        fecha_vencimiento TEXT,
        fecha_recepcion TEXT,
        cantidad_actual REAL DEFAULT 0.0,
        costo_unitario REAL DEFAULT 0.0,
        remision_factura TEXT,
        observaciones TEXT,
        FOREIGN KEY (producto_id) REFERENCES productos(id),
        FOREIGN KEY (bodega_id) REFERENCES bodegas(id)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ordenes_compra (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_oc TEXT UNIQUE NOT NULL,
        proveedor TEXT NOT NULL,
        estado TEXT DEFAULT 'ABIERTA',
        fecha_creacion TEXT NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ordenes_compra_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        oc_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        cantidad_solicitada REAL NOT NULL,
        costo_pactado REAL NOT NULL,
        moneda TEXT DEFAULT 'COP',
        trm REAL DEFAULT 1.0,
        FOREIGN KEY (oc_id) REFERENCES ordenes_compra(id),
        FOREIGN KEY (producto_id) REFERENCES productos(id)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pedidos_venta (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_pedido TEXT UNIQUE NOT NULL,
        cliente TEXT NOT NULL,
        producto_id INTEGER NOT NULL,
        cantidad_solicitada REAL NOT NULL,
        precio_unitario REAL NOT NULL,
        vendedor TEXT NOT NULL,
        fecha_pedido TEXT NOT NULL,
        estado TEXT DEFAULT 'PENDIENTE',
        FOREIGN KEY (producto_id) REFERENCES productos(id)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_kit TEXT UNIQUE NOT NULL,
        nombre_kit TEXT NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kit_componentes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kit_id INTEGER NOT NULL,
        componente_id INTEGER NOT NULL,
        porcentaje_o_cantidad REAL NOT NULL,
        FOREIGN KEY (kit_id) REFERENCES kits(id),
        FOREIGN KEY (componente_id) REFERENCES productos(id)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kardex (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        producto_id INTEGER NOT NULL,
        bodega_id INTEGER NOT NULL,
        tipo_movimiento TEXT NOT NULL,
        cantidad REAL NOT NULL,
        costo_unitario REAL NOT NULL,
        usuario TEXT NOT NULL,
        motivo TEXT,
        lote TEXT,
        documento_ref TEXT,
        FOREIGN KEY (producto_id) REFERENCES productos(id),
        FOREIGN KEY (bodega_id) REFERENCES bodegas(id)
    )""")

    default_users = [
        ("admin", make_hashes("admin123"), "Administrador"),
        ("bodega", make_hashes("bodega123"), "Bodega"),
        ("comercial", make_hashes("comercial123"), "Comercial")
    ]
    for user, pwd, role in default_users:
        cursor.execute("INSERT OR IGNORE INTO usuarios (username, password, rol) VALUES (?, ?, ?)", (user, pwd, role))

    bodegas = ["FINE", "INDUSTRIAL", "MATERIAS PRIMAS", "ENVASES Y DEMÁS"]
    for b in bodegas:
        cursor.execute("INSERT OR IGNORE INTO bodegas (nombre) VALUES (?)", (b,))

    conn.commit()
    conn.close()

init_db()

# ==========================================
# LÓGICA DE NEGOCIO Y AUTENTICACIÓN
# ==========================================
def login_user(username, password):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE username = ? AND password = ?', (username, make_hashes(password)))
    data = c.fetchone()
    conn.close()
    return data

def update_password(username, new_password):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE usuarios SET password = ? WHERE username = ?', (make_hashes(new_password), username))
    conn.commit()
    conn.close()

def calcular_costo_promedio_movil(existencia_actual, costo_prom_actual, cant_nueva, costo_nuevo_cop):
    if existencia_actual <= 0:
        return costo_nuevo_cop
    return ((existencia_actual * costo_prom_actual) + (cant_nueva * costo_nuevo_cop)) / (existencia_actual + cant_nueva)

def obtener_existencia_producto(producto_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT SUM(cantidad_actual) as total FROM lotes WHERE producto_id = ?", (producto_id,))
    res = c.fetchone()['total']
    conn.close()
    return res if res else 0.0

def obtener_oc_pendientes(producto_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT SUM(i.cantidad_solicitada) as oc_cant 
        FROM ordenes_compra_items i 
        JOIN ordenes_compra oc ON i.oc_id = oc.id 
        WHERE i.producto_id = ? AND oc.estado = 'ABIERTA'
    """, (producto_id,))
    res = c.fetchone()['oc_cant']
    conn.close()
    return res if res else 0.0

def registrar_recepcion(producto_id, cantidad, lote_prov, fab_date, exp_date, costo_cop, moneda, trm, costo_ext, remision, obs, usuario, oc_id=None):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
    prod = c.fetchone()
    
    existencia_act = obtener_existencia_producto(producto_id)
    costo_prom_act = prod['costo_promedio']
    
    nuevo_costo_prom = calcular_costo_promedio_movil(existencia_act, costo_prom_act, cantidad, costo_cop)
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("""
        UPDATE productos 
        SET costo_promedio = ?, ultimo_costo = ?, fecha_ultimo_costo = ? 
        WHERE id = ?
    """, (nuevo_costo_prom, costo_cop, fecha_hoy, producto_id))
    
    c.execute("""
        INSERT INTO lotes (producto_id, bodega_id, lote_proveedor, fecha_fabricacion, fecha_vencimiento, fecha_recepcion, cantidad_actual, costo_unitario, remision_factura, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (producto_id, prod['bodega_id'], lote_prov, fab_date, exp_date, fecha_hoy, cantidad, costo_cop, remision, obs))
    
    motivo_txt = f"Recepción Compra ({moneda} TRM: {trm})" if moneda != "COP" else "Recepción Compra"
    c.execute("""
        INSERT INTO kardex (fecha, producto_id, bodega_id, tipo_movimiento, cantidad, costo_unitario, usuario, motivo, lote, documento_ref)
        VALUES (?, ?, ?, 'ENTRADA', ?, ?, ?, ?, ?, ?)
    """, (fecha_hoy, producto_id, prod['bodega_id'], cantidad, costo_cop, usuario, motivo_txt, lote_prov, remision))
    
    if oc_id:
        c.execute("UPDATE ordenes_compra SET estado = 'RECIBIDA' WHERE id = ?", (oc_id,))
        
    conn.commit()
    conn.close()

def registrar_pedido_venta(num_ped, cliente, producto_id, cantidad, precio, vendedor):
    conn = get_connection()
    c = conn.cursor()
    
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO pedidos_venta (numero_pedido, cliente, producto_id, cantidad_solicitada, precio_unitario, vendedor, fecha_pedido, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDIENTE')
    """, (num_ped, cliente, producto_id, cantidad, precio, vendedor, fecha_hoy))
    
    c.execute("UPDATE productos SET comp_venta = comp_venta + ? WHERE id = ?", (cantidad, producto_id))
    conn.commit()
    conn.close()

def despachar_pedido_venta(pedido_id, usuario_despacha):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM pedidos_venta WHERE id = ?", (pedido_id,))
    ped = c.fetchone()
    if not ped or ped['estado'] != 'PENDIENTE':
        conn.close()
        return False, "El pedido ya fue procesado o no existe."
    
    producto_id = ped['producto_id']
    cant_requerida = ped['cantidad_solicitada']
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
    prod = c.fetchone()
    
    c.execute("SELECT * FROM lotes WHERE producto_id = ? AND cantidad_actual > 0 ORDER BY id ASC", (producto_id,))
    lotes = c.fetchall()
    
    cant_descontada = 0.0
    for l in lotes:
        if cant_descontada >= cant_requerida:
            break
        
        faltante = cant_requerida - cant_descontada
        if l['cantidad_actual'] <= faltante:
            tomar = l['cantidad_actual']
            c.execute("UPDATE lotes SET cantidad_actual = 0 WHERE id = ?", (l['id'],))
        else:
            tomar = faltante
            c.execute("UPDATE lotes SET cantidad_actual = cantidad_actual - ? WHERE id = ?", (tomar, l['id']))
            
        cant_descontada += tomar
        
        c.execute("""
            INSERT INTO kardex (fecha, producto_id, bodega_id, tipo_movimiento, cantidad, costo_unitario, usuario, motivo, lote, documento_ref)
            VALUES (?, ?, ?, 'SALIDA', ?, ?, ?, ?, ?, ?)
        """, (fecha_hoy, producto_id, prod['bodega_id'], tomar, prod['costo_promedio'], usuario_despacha, f"Despacho Pedido {ped['numero_pedido']} - Cliente: {ped['cliente']}", l['lote_proveedor'], ped['numero_pedido']))

    c.execute("UPDATE productos SET comp_venta = MAX(0.0, comp_venta - ?) WHERE id = ?", (cant_requerida, producto_id))
    c.execute("UPDATE pedidos_venta SET estado = 'DESPACHADO' WHERE id = ?", (pedido_id,))
    
    conn.commit()
    conn.close()
    return True, "Despacho realizado con éxito."

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
    # MENÚ LATERAL RESTAURADO EXACTAMENTE SEGÚN SOLICITUD
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
            "🛒 Pedidos de Venta",
            "📦 Maestro de Productos y Lotes",
            "🧾 Órdenes de Compra y Recepción",
            "🧪 Kits y Ensambles",
            "🚨 Requerimiento Comercial (MRP)",
            "📜 Kardex e Historial",
            "⚙️ Mi Cuenta y Configuración"
        ]
    )

    conn = get_connection()
    rol = st.session_state['rol']

    # BANNER GENERAL DE NOTIFICACIONES
    try:
        df_p_pend = pd.read_sql_query("SELECT p.numero_pedido, p.cliente, pr.nombre_au, p.cantidad_solicitada, p.vendedor FROM pedidos_venta p JOIN productos pr ON p.producto_id = pr.id WHERE p.estado = 'PENDIENTE'", conn)
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
            df_prods = pd.read_sql_query(query, conn)
        except Exception:
            df_prods = pd.DataFrame()
        
        if busqueda and not df_prods.empty:
            df_prods = df_prods[
                df_prods['codigo_au'].str.contains(busqueda, case=False, na=False) |
                df_prods['codigo_proveedor'].str.contains(busqueda, case=False, na=False) |
                df_prods['nombre_au'].str.contains(busqueda, case=False, na=False)
            ]
            
        if not df_prods.empty:
            prod_sel_id = st.selectbox("Seleccione un producto del resultado:", df_prods['id'].tolist(), 
                                     format_func=lambda x: f"{df_prods[df_prods['id']==x]['codigo_au'].values[0]} | {df_prods[df_prods['id']==x]['nombre_au'].values[0]} (Prov: {df_prods[df_prods['id']==x]['codigo_proveedor'].values[0]})")
            
            p = df_prods[df_prods['id'] == prod_sel_id].iloc[0]
            existencia_total = obtener_existencia_producto(prod_sel_id)
            comp_oc = obtener_oc_pendientes(prod_sel_id)
            
            c = conn.cursor()
            c.execute("SELECT SUM(cantidad) as ent FROM kardex WHERE producto_id = ? AND tipo_movimiento = 'ENTRADA'", (prod_sel_id,))
            r_ent = c.fetchone()['ent']
            tot_entradas = r_ent if r_ent else 0.0
            
            c.execute("SELECT SUM(cantidad) as sal FROM kardex WHERE producto_id = ? AND tipo_movimiento IN ('SALIDA', 'ENSAMBLE', 'MERMA')", (prod_sel_id,))
            r_sal = c.fetchone()['sal']
            tot_salidas = r_sal if r_sal else 0.0

            disp_total = existencia_total - p['comp_venta'] - p['comp_op'] + comp_oc

            st.markdown(f"""
            <div style="background-color:#000080; color:#FFFFFF; font-family:monospace; padding:15px; border-radius:5px;">
            -----------------------------------------------------------------------------------------------------<br>
            | Item &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{p['codigo_au']}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>{p['nombre_au'].upper()}</b><br>
            | Cód Proveedor: <b>{p['codigo_proveedor']}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; PROVEEDOR: <b>{p['proveedor'].upper()}</b><br>
            | Localizacion : <b>{p['nombre_bodega'].upper()}</b><br>
            -----------------------------------------------------------------------------------------------------<br>
            | U.M: <b>{p['unidad_medida']}</b> Clasif.: <b>{p['categoria']} / {p['linea']}</b> &nbsp;|&nbsp; Acumulados Desde &nbsp;&nbsp;&nbsp;&nbsp;: AURANZA-2026<br>
            +-----------------------------------------------+ Total Entradas &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {tot_entradas:,.3f}<br>
            | Existencia Actual : <b>{existencia_total:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Total Salidas &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {tot_salidas:,.3f}<br>
            | Comp. en Venta &nbsp;&nbsp;&nbsp;&nbsp;: <b>{p['comp_venta']:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;+------------------------------------+<br>
            | Comp. en O.P. &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{p['comp_op']:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Costo Prom. Ponderado: $ {p['costo_promedio']:,.2f}<br>
            | Comp. Requisicion : <b>{p['comp_requisicion']:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Ultimo Costo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: $ {p['ultimo_costo']:,.2f}<br>
            | Comp. en O.C. &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{comp_oc:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Fecha Ult. Costo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {p['fecha_ultimo_costo'] if p['fecha_ultimo_costo'] else 'N/A'}<br>
            | <b>Total Disponible &nbsp;: {disp_total:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;+------------------------------------+<br>
            -----------------------------------------------------------------------------------------------------<br>
            | Punto Pedido &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{p['punto_pedido']:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Nivel Maximo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {p['nivel_maximo']:,.3f}<br>
            | Cantidad a Pedir &nbsp;&nbsp;: <b>{max(0.0, p['punto_pedido'] - disp_total):,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Nivel Minimo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {p['nivel_minimo']:,.3f}<br>
            -----------------------------------------------------------------------------------------------------
            </div>
            """, unsafe_allow_html=True)
            
            st.subheader("📦 Trazabilidad por Lotes Activos")
            df_lotes = pd.read_sql_query("SELECT lote_proveedor, cantidad_actual, fecha_fabricacion, fecha_vencimiento, costo_unitario, remision_factura, observaciones FROM lotes WHERE producto_id = ? AND cantidad_actual > 0", conn, params=(prod_sel_id,))
            st.dataframe(df_lotes, use_container_width=True)
        else:
            st.warning("⚠️ No se encontraron productos registrados.")

    elif menu == "🛒 Pedidos de Venta":
        st.title("🛒 Módulo de Pedidos de Venta y Despachos")
        
        sub_vta = st.radio("Acción a realizar:", ["➕ Montar Nuevo Pedido de Venta", "🚚 Control de Despachos y Facturación"], horizontal=True)
        
        if sub_vta == "➕ Montar Nuevo Pedido de Venta":
            st.subheader("Registrar Orden de Pedido Comercial")
            if rol not in ["Administrador", "Comercial"]:
                st.warning("⚠️ Perfil sin autorización para montar pedidos de venta.")
            else:
                try:
                    df_prods_vta = pd.read_sql_query("SELECT id, codigo_au, nombre_au, precio_venta FROM productos", conn)
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
                        precio_ped = c_p4.number_input("Precio de Venta Unitario ($ COP):", value=float(p_sel_info['precio_venta']))
                        
                        st.info(f"📊 **Stock Físico Actual:** {stock_disp:,.2f} KG | **Valor Total Venta:** ${cant_ped * precio_ped:,.2f} COP")
                        
                        if st.form_submit_button("Guardar y Comprometer Inventario"):
                            if not num_ped or not cliente:
                                st.error("❌ Indique el número de pedido y el cliente.")
                            else:
                                try:
                                    registrar_pedido_venta(num_ped, cliente, prod_ped_id, cant_ped, precio_ped, st.session_state['username'])
                                    st.success(f"✅ Pedido {num_ped} registrado. Se sumó {cant_ped} KG a Comprometido en Venta.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al registrar pedido: {e}")

        elif sub_vta == "🚚 Control de Despachos y Facturación":
            st.subheader("Despacho e Impacto en Inventario / Kardex")
            try:
                df_pedidos = pd.read_sql_query("""
                    SELECT p.id, p.numero_pedido, p.cliente, pr.codigo_au, pr.nombre_au, p.cantidad_solicitada, p.precio_unitario, p.vendedor, p.fecha_pedido, p.estado
                    FROM pedidos_venta p
                    JOIN productos pr ON p.producto_id = pr.id
                    ORDER BY p.id DESC
                """, conn)
                
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
            with st.form("crear_producto"):
                st.subheader("Formulario de Creación de Producto AURANZA")
                c1, c2, c3 = st.columns(3)
                codigo_au = c1.text_input("Código AU Interno (ej: AUH0001):")
                codigo_prov = c2.text_input("Código Proveedor (ej: XB0102):")
                nombre_au = c3.text_input("Nombre AU (ej: BAMBU):")
                
                c4, c5, c6 = st.columns(3)
                nombre_prov = c4.text_input("Nombre en Proveedor (ej: BAMBOO):")
                proveedor = c5.text_input("Nombre del Proveedor:")
                bodega_id = c6.selectbox("Bodega Principal Asignada:", [1, 2, 3, 4], format_func=lambda x: ["FINE", "INDUSTRIAL", "MATERIAS PRIMAS", "ENVASES Y DEMÁS"][x-1])
                
                c7, c8, c9 = st.columns(3)
                categoria = c7.selectbox("Categoría:", ["FRAGANCIA", "MATERIA PRIMA", "ENVASE", "EMPAQUE"])
                linea = c8.selectbox("Línea:", ["Fragancias Homecare", "Fragancias Capilares", "Fragancias Óleo", "Fragancias Reeds", "Perfumería Fina Masculina", "Perfumería Fina Femenina", "Perfumería Fina Unisex", "Envases", "Insumos"])
                precio_vta = c9.number_input("Precio de Venta ($):", min_value=0.0)
                
                c10, c11, c12 = st.columns(3)
                pt_pedido = c10.number_input("Punto de Pedido (KG/Unidades):", min_value=0.0)
                nv_min = c11.number_input("Nivel Mínimo:", min_value=0.0)
                nv_max = c12.number_input("Nivel Máximo:", min_value=0.0)
                
                btn_crear = st.form_submit_button("Guardar Producto")
                if btn_crear:
                    try:
                        c = conn.cursor()
                        c.execute("""
                            INSERT INTO productos (codigo_au, codigo_proveedor, nombre_au, nombre_proveedor, proveedor, categoria, linea, bodega_id, precio_venta, punto_pedido, nivel_minimo, nivel_maximo)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (codigo_au, codigo_prov, nombre_au, nombre_prov, proveedor, categoria, linea, bodega_id, precio_vta, pt_pedido, nv_min, nv_max))
                        conn.commit()
                        st.success(f"✅ Producto {codigo_au} - {nombre_au} creado exitosamente!")
                    except Exception as e:
                        st.error(f"Error al crear producto: {e}")

        st.subheader("Inventario Consolidado por Productos")
        try:
            df_prods_all = pd.read_sql_query("SELECT p.codigo_au, p.codigo_proveedor, p.nombre_au, p.proveedor, b.nombre as bodega, p.costo_promedio, p.ultimo_costo, p.precio_venta FROM productos p JOIN bodegas b ON p.bodega_id = b.id", conn)
            st.dataframe(df_prods_all, use_container_width=True)
        except Exception:
            st.info("Aún no hay productos registrados.")

    elif menu == "🧾 Órdenes de Compra y Recepción":
        st.title("🧾 Gestión de Compras y Recepciones")
        
        sub_oc = st.radio("Acción a realizar:", ["Emitir Órden de Compra (OC)", "📦 Recepción de Mercancía en Bodega"], horizontal=True)

        if sub_oc == "Emitir Órden de Compra (OC)":
            st.subheader("Generar Nueva Orden de Compra")
            if rol not in ["Administrador"]:
                st.warning("⚠️ Emisión de Compras restringida a perfil Administrador.")
            else:
                try:
                    df_prods = pd.read_sql_query("SELECT id, codigo_au, codigo_proveedor, nombre_au, nombre_proveedor, proveedor FROM productos", conn)
                except Exception:
                    df_prods = pd.DataFrame()
                
                if df_prods.empty:
                    st.warning("⚠️ Primero cree productos en el menú 'Maestro de Productos y Lotes'.")
                else:
                    num_oc = st.text_input("Número de OC (ej: OC-0001):")
                    prod_oc_id = st.selectbox("Seleccionar Producto:", df_prods['id'].tolist(), format_func=lambda x: f"{df_prods[df_prods['id']==x]['nombre_au'].values[0]} | Proveedor: {df_prods[df_prods['id']==x]['proveedor'].values[0]}")
                    
                    col_a, col_b, col_c = st.columns(3)
                    cant_oc = col_a.number_input("Cantidad a Solicitar (KG/Unidades):", min_value=0.1)
                    moneda_oc = col_b.selectbox("Moneda O.C.:", ["COP", "USD", "EUR"])
                    trm_oc = col_c.number_input("TRM Proyectada (COP):", value=4100.0 if moneda_oc != "COP" else 1.0)
                    
                    costo_unit_ext = st.number_input(f"Costo Unitario en {moneda_oc}:", min_value=0.0)
                    costo_cop_calc = costo_unit_ext * trm_oc if moneda_oc != "COP" else costo_unit_ext
                    st.info(f"💵 Costo Equivalente Estimado: **${costo_cop_calc:,.2f} COP / Unidad**")

                    prod_info = df_prods[df_prods['id']==prod_oc_id].iloc[0]
                    st.info(f"📋 **Documento Proveedor:** {prod_info['codigo_proveedor']} - {prod_info['nombre_proveedor']} | **Interno AU:** {prod_info['codigo_au']} - {prod_info['nombre_au']}")
                    
                    if st.button("Emitir Orden de Compra"):
                        c = conn.cursor()
                        c.execute("INSERT INTO ordenes_compra (numero_oc, proveedor, fecha_creacion) VALUES (?, ?, ?)", (num_oc, prod_info['proveedor'], datetime.now().strftime("%Y-%m-%d")))
                        oc_id = c.lastrowid
                        c.execute("INSERT INTO ordenes_compra_items (oc_id, producto_id, cantidad_solicitada, costo_pactado, moneda, trm) VALUES (?, ?, ?, ?, ?, ?)", (oc_id, prod_oc_id, cant_oc, costo_cop_calc, moneda_oc, trm_oc))
                        conn.commit()
                        st.success(f"✅ OC {num_oc} emitida correctamente.")

        elif sub_oc == "📦 Recepción de Mercancía en Bodega":
            st.subheader("Entrada de Mercancía a Bodega (Recepción)")
            if rol not in ["Administrador", "Bodega"]:
                st.warning("⚠️ Modulo de recepción reservado para perfiles Bodega o Administrador.")
            else:
                try:
                    df_ocs = pd.read_sql_query("SELECT oc.id, oc.numero_oc, oc.proveedor, i.producto_id, i.cantidad_solicitada, i.costo_pactado, i.moneda, i.trm FROM ordenes_compra oc JOIN ordenes_compra_items i ON oc.id = i.oc_id WHERE oc.estado = 'ABIERTA'", conn)
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
                        st.write("<b>Costo y Conversión TRM Informativa</b>", unsafe_allow_html=True)
                        cm1, cm2, cm3 = st.columns(3)
                        moneda_rx = cm1.selectbox("Moneda Factura:", ["COP", "USD", "EUR"], index=["COP", "USD", "EUR"].index(item_oc['moneda']))
                        trm_rx = cm2.number_input("TRM Aplicada Factura:", value=float(item_oc['trm']))
                        costo_ext_rx = cm3.number_input(f"Costo Facturado en {moneda_rx}:", value=float(item_oc['costo_pactado'] / item_oc['trm']) if item_oc['trm'] > 0 else float(item_oc['costo_pactado']))
                        
                        costo_cop_final = costo_ext_rx * trm_rx if moneda_rx != "COP" else costo_ext_rx
                        st.success(f"💰 **Costo Final de Entrada a Valoración:** ${costo_cop_final:,.2f} COP / KG")
                        
                        st.markdown("---")
                        lote_prov = st.text_input("Número de Lote del Proveedor:")
                        
                        cd1, cd2 = st.columns(2)
                        fab_date = cd1.date_input("Fecha de Fabricación:")
                        exp_date = cd2.date_input("Fecha de Vencimiento:")
                        
                        obs_rx = st.text_area("Observaciones de Recepción:")
                        
                        if st.form_submit_button("Confirmar Entrada y Actualizar Costo Promedio Móvil"):
                            registrar_recepcion(item_oc['producto_id'], cant_rx, lote_prov, str(fab_date), str(exp_date), costo_cop_final, moneda_rx, trm_rx, costo_ext_rx, remision, obs_rx, st.session_state['username'], oc_id=item_oc['id'])
                            st.success("✅ Entrada registrada exitosamente. Costo promedio ponderado móvil actualizado.")

    elif menu == "🧪 Kits y Ensambles":
        st.title("🧪 Creación y Ensamble de Kits")
        
        st.subheader("Fórmulas de Ensamble y Costo Teórico Actualizado")
        try:
            df_prods = pd.read_sql_query("SELECT id, codigo_au, nombre_au, costo_promedio FROM productos", conn)
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
                        c.execute("INSERT INTO kits (codigo_kit, nombre_kit) VALUES (?, ?)", (cod_kit, nom_kit))
                        kit_id = c.lastrowid
                        c.execute("INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad) VALUES (?, ?, ?)", (kit_id, comp1, prop1))
                        c.execute("INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad) VALUES (?, ?, ?)", (kit_id, comp2, prop2))
                        c.execute("INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad) VALUES (?, ?, ?)", (kit_id, comp3, prop3))
                        conn.commit()
                        st.success("✅ Fórmula de Kit guardada.")

        st.subheader("Análisis de Costo y Margen Teórico por Kit")
        try:
            df_kits_list = pd.read_sql_query("SELECT * FROM kits", conn)
            for idx, k_item in df_kits_list.iterrows():
                df_comp_k = pd.read_sql_query("""
                    SELECT kc.porcentaje_o_cantidad, p.costo_promedio, p.nombre_au
                    FROM kit_componentes kc
                    JOIN productos p ON kc.componente_id = p.id
                    WHERE kc.kit_id = ?
                """, conn, params=(k_item['id'],))
                
                costo_mezcla_kg = sum(df_comp_k['porcentaje_o_cantidad'] * df_comp_k['costo_promedio'])
                st.info(f"🧪 **{k_item['codigo_kit']} - {k_item['nombre_kit']}** | Costo Promedio Móvil Mezcla: **${costo_mezcla_kg:,.2f} COP / KG**")
        except Exception:
            st.info("Aún no hay kits creados.")

    elif menu == "🚨 Requerimiento Comercial (MRP)":
        st.title("🚨 Motor MRP: Análisis de Materias Primas y Empaques")
        
        try:
            df_kits = pd.read_sql_query("SELECT * FROM kits", conn)
        except Exception:
            df_kits = pd.DataFrame()

        if df_kits.empty:
            st.warning("⚠️ No existen Kits registrados para simular el MRP. Regístrelos en 'Kits y Ensambles'.")
        else:
            kit_sel = st.selectbox("Seleccionar Kit a Comercializar:", df_kits['id'].tolist(), format_func=lambda x: f"{df_kits[df_kits['id']==x]['codigo_kit'].values[0]} - {df_kits[df_kits['id']==x]['nombre_kit'].values[0]}")
            cant_solicitada = st.number_input("Cantidad Requerida por Cliente (KG):", value=300.0)
            
            if st.button("🔍 Evaluar Disponibilidad y Generar Requerimientos"):
                st.subheader("1. Evaluación de Materias Primas")
                df_comps = pd.read_sql_query("""
                    SELECT kc.componente_id, p.codigo_au, p.nombre_au, kc.porcentaje_o_cantidad, p.costo_promedio
                    FROM kit_componentes kc
                    JOIN productos p ON kc.componente_id = p.id
                    WHERE kc.kit_id = ?
                """, conn, params=(kit_sel,))
                
                costo_mezcla_total = 0.0
                
                for idx, row in df_comps.iterrows():
                    necesario = row['porcentaje_o_cantidad'] * cant_solicitada
                    disponible_fisico = obtener_existencia_producto(row['componente_id'])
                    oc_pendientes = obtener_oc_pendientes(row['componente_id'])
                    disponible_neto = disponible_fisico + oc_pendientes
                    
                    costo_comp = necesario * row['costo_promedio']
                    costo_mezcla_total += costo_comp
                    
                    if disponible_neto >= necesario:
                        st.success(f"🟢 **{row['nombre_au']} ({row['codigo_au']})**: Requerido: {necesario:.2f} KG | Stock Físico: {disponible_fisico:.2f} KG | OC Abiertas: {oc_pendientes:.2f} KG")
                    else:
                        faltante_neto = necesario - disponible_neto
                        st.error(f"🔴 **{row['nombre_au']} ({row['codigo_au']})**: Requerido: {necesario:.2f} KG | Stock Físico: {disponible_fisico:.2f} KG | OC Abiertas: {oc_pendientes:.2f} KG | **FALTANTE NETO A COMPRAR: {faltante_neto:.2f} KG**")
                
                st.subheader("2. Regla de Empaques y Evaluación en Bodega 4")
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
        st.title("📜 Trazabilidad Completa / Kardex Auditable")
        try:
            df_kardex = pd.read_sql_query("""
                SELECT k.fecha, p.codigo_au, p.nombre_au, b.nombre as bodega, k.tipo_movimiento, k.cantidad, k.costo_unitario, k.usuario, k.motivo, k.lote, k.documento_ref
                FROM kardex k
                LEFT JOIN productos p ON k.producto_id = p.id
                LEFT JOIN bodegas b ON k.bodega_id = b.id
                ORDER BY k.id DESC
            """, conn)
            if df_kardex.empty:
                st.info("Aún no hay movimientos registrados en el Kardex.")
            else:
                st.dataframe(df_kardex, use_container_width=True)
        except Exception:
            st.info("Aún no se han generado registros en el Kardex.")

    elif menu == "⚙️ Mi Cuenta y Configuración":
        st.title("⚙️ Gestión de Claves y Usuarios")
        
        st.subheader("🔑 Cambiar mi Contraseña")
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

    conn.close()

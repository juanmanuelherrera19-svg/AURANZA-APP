import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# ==========================================
# CONFIGURACIÓN E INICIALIZACIÓN DE BD
# ==========================================
st.set_page_config(page_title="AURANZA SAS - ERP/MRP System", layout="wide", page_icon="🧪")

def get_connection():
    conn = sqlite3.connect("auranza_inventario.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
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
        FOREIGN KEY (oc_id) REFERENCES ordenes_compra(id),
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
        FOREIGN KEY (producto_id) REFERENCES productos(id),
        FOREIGN KEY (bodega_id) REFERENCES bodegas(id)
    )""")

    bodegas = ["FINE", "INDUSTRIAL", "MATERIAS PRIMAS", "ENVASES Y DEMÁS"]
    for b in bodegas:
        cursor.execute("INSERT OR IGNORE INTO bodegas (nombre) VALUES (?)", (b,))

    conn.commit()
    conn.close()

init_db()

# ==========================================
# LÓGICA DE NEGOCIO Y CÁLCULOS
# ==========================================
def calcular_costo_promedio(existencia_actual, costo_prom_actual, cant_nueva, costo_nuevo):
    if (existencia_actual + cant_nueva) <= 0:
        return costo_nuevo
    return ((existencia_actual * costo_prom_actual) + (cant_nueva * costo_nuevo)) / (existencia_actual + cant_nueva)

def obtener_existencia_producto(producto_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT SUM(cantidad_actual) as total FROM lotes WHERE producto_id = ?", (producto_id,))
    res = c.fetchone()['total']
    conn.close()
    return res if res else 0.0

def registrar_recepcion(producto_id, cantidad, lote_prov, fab_date, exp_date, costo_nuevo, usuario, oc_id=None):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
    prod = c.fetchone()
    
    existencia_act = obtener_existencia_producto(producto_id)
    costo_prom_act = prod['costo_promedio']
    nuevo_costo_prom = calcular_costo_promedio(existencia_act, costo_prom_act, cantidad, costo_nuevo)
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("""
        UPDATE productos 
        SET costo_promedio = ?, ultimo_costo = ?, fecha_ultimo_costo = ? 
        WHERE id = ?
    """, (nuevo_costo_prom, costo_nuevo, fecha_hoy, producto_id))
    
    c.execute("""
        INSERT INTO lotes (producto_id, bodega_id, lote_proveedor, fecha_fabricacion, fecha_vencimiento, fecha_recepcion, cantidad_actual, costo_unitario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (producto_id, prod['bodega_id'], lote_prov, fab_date, exp_date, fecha_hoy, cantidad, costo_nuevo))
    
    c.execute("""
        INSERT INTO kardex (fecha, producto_id, bodega_id, tipo_movimiento, cantidad, costo_unitario, usuario, motivo, lote)
        VALUES (?, ?, ?, 'ENTRADA', ?, ?, ?, 'Recepción de Compra', ?)
    """, (fecha_hoy, producto_id, prod['bodega_id'], cantidad, costo_nuevo, usuario, lote_prov))
    
    if oc_id:
        c.execute("UPDATE ordenes_compra SET estado = 'RECIBIDA' WHERE id = ?", (oc_id,))
        
    conn.commit()
    conn.close()

# ==========================================
# INTERFAZ Y NAVEGACIÓN
# ==========================================
st.sidebar.title("🧪 AURANZA SAS ERP")
st.sidebar.markdown("---")
rol = st.sidebar.selectbox("👤 Perfil de Usuario:", ["Administrador", "Bodega", "Comercial"])

menu = st.sidebar.radio("Navegación Módulos:", [
    "📊 Ficha de Producto",
    "📦 Maestro de Productos y Lotes",
    "📑 Órdenes de Compra y Recepción",
    "🧪 Kits y Ensambles",
    "🚨 Requerimiento Comercial (MRP)",
    "📜 Kardex e Historial"
])

conn = get_connection()

if menu == "📊 Ficha de Producto":
    st.title("📊 Consulta General de Producto / Inventario")
    busqueda = st.text_input("🔍 Buscar por Código AU, Código Proveedor o Nombre:")
    
    query = """
    SELECT p.*, b.nombre as nombre_bodega 
    FROM productos p 
    JOIN bodegas b ON p.bodega_id = b.id
    """
    df_prods = pd.read_sql_query(query, conn)
    
    if busqueda:
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
        
        c = conn.cursor()
        c.execute("SELECT SUM(cantidad) as ent FROM kardex WHERE producto_id = ? AND tipo_movimiento = 'ENTRADA'", (prod_sel_id,))
        r_ent = c.fetchone()['ent']
        tot_entradas = r_ent if r_ent else 0.0
        
        c.execute("SELECT SUM(cantidad) as sal FROM kardex WHERE producto_id = ? AND tipo_movimiento IN ('SALIDA', 'ENSAMBLE', 'MERMA')", (prod_sel_id,))
        r_sal = c.fetchone()['sal']
        tot_salidas = r_sal if r_sal else 0.0

        c.execute("""
            SELECT SUM(i.cantidad_solicitada) as oc_cant 
            FROM ordenes_compra_items i 
            JOIN ordenes_compra oc ON i.oc_id = oc.id 
            WHERE i.producto_id = ? AND oc.estado = 'ABIERTA'
        """, (prod_sel_id,))
        r_oc = c.fetchone()['oc_cant']
        comp_oc = r_oc if r_oc else 0.0

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
        | Comp. en O.C. &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b>{comp_oc:,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;+------------------------------------+<br>
        | <b>Total Disponible &nbsp;: {(existencia_total + comp_oc):,.3f}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Costo Prom. Unitario : $ {p['costo_promedio']:,.2f}<br>
        | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Ultimo Costo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: $ {p['ultimo_costo']:,.2f}<br>
        | &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|&nbsp; Fecha Ult. Costo &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: {p['fecha_ultimo_costo'] if p['fecha_ultimo_costo'] else 'N/A'}<br>
        -----------------------------------------------------------------------------------------------------
        </div>
        """, unsafe_allow_html=True)
        
        st.subheader("📦 Detalle por Lotes Activos")
        df_lotes = pd.read_sql_query("SELECT lote_proveedor, cantidad_actual, fecha_fabricacion, fecha_vencimiento, costo_unitario FROM lotes WHERE producto_id = ? AND cantidad_actual > 0", conn, params=(prod_sel_id,))
        st.dataframe(df_lotes, use_container_width=True)

elif menu == "📦 Maestro de Productos y Lotes":
    st.title("📦 Crear y Administrar Productos")
    
    if rol != "Administrador":
        st.warning("⚠️ Su rol solo le permite consultar la información.")
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
            
            btn_crear = st.form_submit_button("Guardar Producto")
            if btn_crear:
                try:
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO productos (codigo_au, codigo_proveedor, nombre_au, nombre_proveedor, proveedor, categoria, linea, bodega_id, precio_venta)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (codigo_au, codigo_prov, nombre_au, nombre_prov, proveedor, categoria, linea, bodega_id, precio_vta))
                    conn.commit()
                    st.success(f"✅ Producto {codigo_au} - {nombre_au} creado exitosamente!")
                except Exception as e:
                    st.error(f"Error al crear producto: {e}")

    st.subheader("Inventario Consolidado por Productos")
    df_prods_all = pd.read_sql_query("SELECT p.codigo_au, p.codigo_proveedor, p.nombre_au, p.proveedor, b.nombre as bodega, p.costo_promedio, p.precio_venta FROM productos p JOIN bodegas b ON p.bodega_id = b.id", conn)
    st.dataframe(df_prods_all, use_container_width=True)

elif menu == "📑 Órdenes de Compra y Recepción":
    st.title("📑 Gestión de Compras y Recepciones")
    
    tab1, tab2 = st.tabs(["Emitir Órden de Compra (OC)", "📦 Recepción de Mercancía en Bodega"])
    
    with tab1:
        st.subheader("Generar Nueva Orden de Compra")
        df_prods = pd.read_sql_query("SELECT id, codigo_au, codigo_proveedor, nombre_au, nombre_proveedor, proveedor FROM productos", conn)
        
        if not df_prods.empty:
            num_oc = st.text_input("Número de OC (ej: OC-0001):")
            prod_oc_id = st.selectbox("Seleccionar Producto:", df_prods['id'].tolist(), format_func=lambda x: f"{df_prods[df_prods['id']==x]['nombre_au'].values[0]} | Proveedor: {df_prods[df_prods['id']==x]['proveedor'].values[0]}")
            cant_oc = st.number_input("Cantidad a Solicitar (KG):", min_value=0.1)
            costo_oc = st.number_input("Costo Pactado / Factura Proveedor ($):", min_value=0.0)
            
            prod_info = df_prods[df_prods['id']==prod_oc_id].iloc[0]
            st.info(f"📋 **Vista para Proveedor:** {prod_info['codigo_proveedor']} - {prod_info['nombre_proveedor']} | **Interno AU:** {prod_info['codigo_au']} - {prod_info['nombre_au']}")
            
            if st.button("Emitir Orden de Compra"):
                c = conn.cursor()
                c.execute("INSERT INTO ordenes_compra (numero_oc, proveedor, fecha_creacion) VALUES (?, ?, ?)", (num_oc, prod_info['proveedor'], datetime.now().strftime("%Y-%m-%d")))
                oc_id = c.lastrowid
                c.execute("INSERT INTO ordenes_compra_items (oc_id, producto_id, cantidad_solicitada, costo_pactado) VALUES (?, ?, ?, ?)", (oc_id, prod_oc_id, cant_oc, costo_oc))
                conn.commit()
                st.success(f"✅ OC {num_oc} emitida correctamente.")

    with tab2:
        st.subheader("Entrada de Mercancía a Bodega")
        if rol == "Comercial":
            st.error("🚫 El perfil Comercial no puede registrar entradas de inventario.")
        else:
            df_ocs = pd.read_sql_query("SELECT oc.id, oc.numero_oc, oc.proveedor, i.producto_id, i.cantidad_solicitada, i.costo_pactado FROM ordenes_compra oc JOIN ordenes_compra_items i ON oc.id = i.oc_id WHERE oc.estado = 'ABIERTA'", conn)
            
            if df_ocs.empty:
                st.info("No hay Órdenes de Compra abiertas pendientes por recibir.")
            else:
                oc_sel = st.selectbox("Seleccionar OC por Recibir:", df_ocs['id'].tolist(), format_func=lambda x: f"OC: {df_ocs[df_ocs['id']==x]['numero_oc'].values[0]} - Prov: {df_ocs[df_ocs['id']==x]['proveedor'].values[0]}")
                item_oc = df_ocs[df_ocs['id']==oc_sel].iloc[0]
                
                with st.form("form_rx"):
                    st.write(f"Recibiendo producto ID: {item_oc['producto_id']} | Cantidad solicitada: {item_oc['cantidad_solicitada']} KG")
                    cant_rx = st.number_input("Cantidad Real Recibida (KG):", value=float(item_oc['cantidad_solicitada']))
                    costo_rx = st.number_input("Costo Facturado Final ($):", value=float(item_oc['costo_pactado']))
                    lote_prov = st.text_input("Número de Lote de Proveedor:")
                    fab_date = st.date_input("Fecha de Fabricación:")
                    exp_date = st.date_input("Fecha de Vencimiento:")
                    user_rx = st.text_input("Nombre de quien recibe (Bodega):")
                    
                    if st.form_submit_button("Confirmar Entrada y Actualizar Costo Promedio"):
                        registrar_recepcion(item_oc['producto_id'], cant_rx, lote_prov, str(fab_date), str(exp_date), costo_rx, user_rx, oc_id=item_oc['id'])
                        st.success("✅ Entrada registrada exitosamente. Costo promedio móvil actualizado.")

elif menu == "🧪 Kits y Ensambles":
    st.title("🧪 Creación y Ensamble de Kits")
    
    st.subheader("Fórmulas de Ensamble")
    df_prods = pd.read_sql_query("SELECT id, codigo_au, nombre_au, costo_promedio FROM productos", conn)
    
    with st.expander("➕ Crear Nueva Fórmula de Kit"):
        cod_kit = st.text_input("Código del Kit / Producto Final (ej: AU0010):")
        nom_kit = st.text_input("Nombre Comercial Kit (ej: FRAGANCIA BAMBU 1KG):")
        
        st.write("Seleccione Componentes Químicos (Proporción para 1 KG):")
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

elif menu == "🚨 Requerimiento Comercial (MRP)":
    st.title("🚨 Cálculo de Necesidades de Producción y Empaque")
    
    df_kits = pd.read_sql_query("SELECT * FROM kits", conn)
    if not df_kits.empty:
        kit_sel = st.selectbox("Seleccionar Kit a Comercializar:", df_kits['id'].tolist(), format_func=lambda x: f"{df_kits[df_kits['id']==x]['codigo_kit'].values[0]} - {df_kits[df_kits['id']==x]['nombre_kit'].values[0]}")
        cant_solicitada = st.number_input("Cantidad Requerida por Cliente (KG):", value=300.0)
        
        if st.button("🔍 Evaluar Disponibilidad de Inventario y Empaques"):
            st.subheader("1. Análisis de Materias Primas")
            df_comps = pd.read_sql_query("""
                SELECT kc.componente_id, p.codigo_au, p.nombre_au, kc.porcentaje_o_cantidad, p.costo_promedio
                FROM kit_componentes kc
                JOIN productos p ON kc.componente_id = p.id
                WHERE kc.kit_id = ?
            """, conn, params=(kit_sel,))
            
            costo_mezcla_total = 0.0
            
            for idx, row in df_comps.iterrows():
                necesario = row['porcentaje_o_cantidad'] * cant_solicitada
                disponible = obtener_existencia_producto(row['componente_id'])
                costo_comp = necesario * row['costo_promedio']
                costo_mezcla_total += costo_comp
                
                if disponible >= necesario:
                    st.success(f"🟢 **{row['nombre_au']} ({row['codigo_au']})**: Requerido: {necesario:.2f} KG | Disponible: {disponible:.2f} KG")
                else:
                    faltante_cant = necesario - disponible
                    st.error(f"🔴 **{row['nombre_au']} ({row['codigo_au']})**: Requerido: {necesario:.2f} KG | Disponible: {disponible:.2f} KG | **FALTAN: {faltante_cant:.2f} KG**")
            
            st.subheader("2. Regla Automática de Empaques (Bodega 4)")
            if cant_solicitada <= 2:
                unidades_envase = 1
                tipo_envase = "Envase 2 KG"
            elif cant_solicitada <= 5:
                unidades_envase = 1
                tipo_envase = "Envase 5 KG"
            else:
                unidades_envase = int(cant_solicitada // 20) + (1 if cant_solicitada % 20 != 0 else 0)
                tipo_envase = "Envase 20 KG"
                
            st.info(f"📦 Para entregar {cant_solicitada} KG se requieren: **{unidades_envase} Unidades de {tipo_envase} + Tapa + Tapón**.")
            st.metric("Costo Estimado Mezcla Materias Primas", f"${costo_mezcla_total:,.2f} COP")

elif menu == "📜 Kardex e Historial":
    st.title("📜 Trazabilidad Completa / Kardex")
    df_kardex = pd.read_sql_query("""
        SELECT k.fecha, p.codigo_au, p.nombre_au, b.nombre as bodega, k.tipo_movimiento, k.cantidad, k.costo_unitario, k.usuario, k.motivo, k.lote
        FROM kardex k
        JOIN productos p ON k.producto_id = p.id
        JOIN bodegas b ON k.bodega_id = b.id
        ORDER BY k.id DESC
    """, conn)
    st.dataframe(df_kardex, use_container_width=True)

conn.close()

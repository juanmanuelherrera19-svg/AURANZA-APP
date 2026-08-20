import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
from supabase import create_client, Client
from fpdf import FPDF

# ==========================================
# CONFIGURACIÓN E INICIALIZACIÓN DE CONEXIÓN
# ==========================================
st.set_page_config(page_title="AURANZA SAS - ERP/MRP System", layout="wide", page_icon="🧪")

@st.cache_resource
def init_supabase() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Error al conectar con Supabase: {e}. Verifique la configuración de Secrets en Streamlit.")
        st.stop()

supabase = init_supabase()

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# FUNCIONES DE BASE DE DATOS Y KARDEX
# ==========================================
def login_user(username, password):
    hashed = make_hashes(password)
    res = supabase.table("usuarios").select("*").eq("username", username).eq("password", hashed).execute()
    return res.data[0] if res.data else None

def registrar_kardex(producto_id, lote_id, tipo_mov, cantidad, usuario, observacion):
    supabase.table("kardex").insert({
        "producto_id": producto_id,
        "lote_id": lote_id,
        "tipo_movimiento": tipo_mov,
        "cantidad": cantidad,
        "usuario": usuario,
        "observacion": observacion
    }).execute()

# ==========================================
# GENERADOR DE PDF OFICIAL - ORDEN DE COMPRA
# ==========================================
class PDF_OC(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'AURANZA S.A.S.', 0, 1, 'L')
        self.set_font('Arial', '', 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, 'NIT: 901.458.922-1 | PBX: +57 (602) 889-0000', 0, 1, 'L')
        self.cell(0, 4, 'Email: compras@auranza.com | Jamundí, Valle del Cauca - Colombia', 0, 1, 'L')
        self.ln(4)
        self.set_draw_color(0, 51, 102)
        self.set_linewidth(0.8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Página {self.page_no()} - Documento Oficial de Compra Emitido por Sistema ERP Auranza', 0, 0, 'C')

def generar_pdf_oc(num_oc, proveedor, producto_nombre, codigo_prov, cantidad, unidad, costo_unit, moneda, trm, fecha):
    pdf = PDF_OC()
    pdf.add_page()
    
    # Encabezado OC
    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 8, f'ORDEN DE COMPRA N°: {num_oc}', 0, 1, 'R')
    pdf.set_font('Arial', '', 10)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 5, f'Fecha de Emisión: {fecha}', 0, 1, 'R')
    pdf.ln(5)

    # Bloque Proveedor
    pdf.set_fill_color(240, 244, 248)
    pdf.set_font('Arial', 'B', 11)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 7, ' INFORMACIÓN DEL PROVEEDOR', 1, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, f' Razon Social / Proveedor: {proveedor}', 1, 1, 'L')
    pdf.ln(6)

    # Tabla de Detalle
    pdf.set_fill_color(0, 51, 102)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Arial', 'B', 9)
    
    pdf.cell(30, 7, 'Cod. Prov.', 1, 0, 'C', fill=True)
    pdf.cell(75, 7, 'Descripción Materia Prima / Insumo', 1, 0, 'C', fill=True)
    pdf.cell(25, 7, 'Cantidad', 1, 0, 'C', fill=True)
    pdf.cell(30, 7, f'V. Unit ({moneda})', 1, 0, 'C', fill=True)
    pdf.cell(30, 7, f'Total ({moneda})', 1, 1, 'C', fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Arial', '', 9)
    total_item = cantidad * costo_unit
    
    pdf.cell(30, 7, str(codigo_prov), 1, 0, 'C')
    pdf.cell(75, 7, str(producto_nombre)[:38], 1, 0, 'L')
    pdf.cell(25, 7, f'{cantidad:,.2f} {unidad}', 1, 0, 'C')
    pdf.cell(30, 7, f'${costo_unit:,.2f}', 1, 0, 'R')
    pdf.cell(30, 7, f'${total_item:,.2f}', 1, 1, 'R')

    pdf.ln(4)
    if moneda != "COP":
        pdf.set_font('Arial', 'I', 8)
        pdf.cell(0, 5, f'* Nota: TRM pactada para liquidación: ${trm:,.2f} COP por {moneda}', 0, 1, 'L')

    pdf.ln(20)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(90, 6, '________________________________________', 0, 0, 'C')
    pdf.cell(90, 6, '________________________________________', 0, 1, 'C')
    pdf.cell(90, 5, 'Aprobado - Departamento de Compras', 0, 0, 'C')
    pdf.cell(90, 5, 'Aceptado - Firma Representante Proveedor', 0, 1, 'C')

    return pdf.output(dest='S').encode('latin-1')

# ==========================================
# CONTROL DE SESIÓN Y AUTENTICACIÓN
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['username'] = ''
    st.session_state['rol'] = ''

if not st.session_state['logged_in']:
    st.title("🧪 AURANZA SAS - ERP/MRP System")
    st.subheader("🔐 Acceso al Sistema Cifrado")
    
    with st.form("login_form"):
        user = st.text_input("Usuario Acceso")
        pwd = st.text_input("Contraseña", type="password")
        submit_btn = st.form_submit_button("Ingresar al ERP")
        
        if submit_btn:
            userdata = login_user(user, pwd)
            if userdata:
                st.session_state['logged_in'] = True
                st.session_state['username'] = userdata['username']
                st.session_state['rol'] = userdata['rol']
                st.success(f"Bienvenido {userdata['username']} ({userdata['rol']})")
                st.rerun()
            else:
                st.error("❌ Credenciales incorrectas. Verifique usuario y contraseña.")
else:
    st.sidebar.title("🧪 AURANZA SAS ERP")
    st.sidebar.markdown(f"👤 **Usuario Activo:** `{st.session_state['username']}`")
    st.sidebar.markdown(f"🛡️ **Rol Asignado:** `{st.session_state['rol']}`")
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state['logged_in'] = False
        st.session_state['username'] = ''
        st.session_state['rol'] = ''
        st.rerun()

    menu = st.sidebar.radio("Módulos del Sistema:", [
        "📊 Dashboard General",
        "📦 Maestro de Productos y Fórmulas",
        "🏷️ Gestión de Lotes e Inventario",
        "🏭 Planificación y Producción (MRP)",
        "📑 Órdenes de Compra y Generación PDF",
        "📜 Historial Kardex de Movimientos",
        "👥 Administración de Usuarios"
    ])

    # ==========================================
    # MÓDULO 1: DASHBOARD
    # ==========================================
    if menu == "📊 Dashboard General":
        st.title("📊 Panel de Control Operativo - Auranza SAS")
        st.markdown("Indicadores de estado general del sistema en tiempo real.")
        
        res_p = supabase.table("productos").select("id").execute()
        res_l = supabase.table("lotes").select("cantidad_actual").execute()
        res_oc = supabase.table("ordenes_compra").select("id").execute()

        col1, col2, col3 = st.columns(3)
        col1.metric("Productos / Insumos Registrados", len(res_p.data) if res_p.data else 0)
        
        total_inv = sum([item['cantidad_actual'] for item in res_l.data]) if res_l.data else 0
        col2.metric("Total Unidades en Stock", f"{total_inv:,.2f}")
        col3.metric("Órdenes de Compra Generadas", len(res_oc.data) if res_oc.data else 0)

    # ==========================================
    # MÓDULO 2: MAESTRO DE PRODUCTOS
    # ==========================================
    elif menu == "📦 Maestro de Productos y Fórmulas":
        st.title("📦 Maestro de Productos y Formulaciones")
        
        tab1, tab2 = st.tabs(["Crear Producto / Materia Prima", "Catálogo Existente"])
        
        with tab1:
            with st.form("nuevo_producto"):
                col1, col2 = st.columns(2)
                cod_au = col1.text_input("Código Auranza (ej: MP-001 / PT-100):")
                cod_prov = col2.text_input("Código Proveedor:")
                nom_au = col1.text_input("Nombre Auranza:")
                nom_prov = col2.text_input("Nombre Proveedor:")
                proveedor = col1.text_input("Proveedor Principal:")
                um = col2.selectbox("Unidad de Medida:", ["Kg", "Litros", "Gramos", "Unidades"])
                costo = col1.number_input("Costo Estándar (COP):", min_value=0.0)
                precio = col2.number_input("Precio de Venta (COP):", min_value=0.0)
                stock_seg = col1.number_input("Stock de Seguridad:", min_value=0.0)
                tam_lote = col2.number_input("Tamaño de Lote Estándar:", min_value=1.0, value=1.0)
                lead_time = col1.number_input("Lead Time (Días entrega):", min_value=1, value=1)
                es_form = col2.checkbox("¿Es Producto Terminado / Formulado?")
                
                btn_crear = st.form_submit_button("Guardar en Base de Datos")
                if btn_crear:
                    supabase.table("productos").insert({
                        "codigo_au": cod_au,
                        "codigo_proveedor": cod_prov,
                        "nombre_au": nom_au,
                        "nombre_proveedor": nom_prov,
                        "proveedor": proveedor,
                        "unidad_medida": um,
                        "costo_estandar": costo,
                        "precio_venta": precio,
                        "stock_seguridad": stock_seg,
                        "tamano_lote": tam_lote,
                        "lead_time_dias": lead_time,
                        "es_formula": es_form
                    }).execute()
                    st.success(f"✅ Producto '{nom_au}' registrado exitosamente.")

        with tab2:
            res = supabase.table("productos").select("*").execute()
            if res.data:
                st.dataframe(pd.DataFrame(res.data), use_container_width=True)
            else:
                st.info("No hay productos registrados en la base de datos.")

    # ==========================================
    # MÓDULO 3: GESTIÓN DE LOTES E INVENTARIO
    # ==========================================
    elif menu == "🏷️ Gestión de Lotes e Inventario":
        st.title("🏷️ Control de Lotes e Inventario Físico")
        
        res_p = supabase.table("productos").select("id, nombre_au, codigo_au").execute()
        if not res_p.data:
            st.warning("⚠️ Debe registrar productos en el Maestro antes de gestionar lotes.")
        else:
            df_p = pd.DataFrame(res_p.data)
            
            st.subheader("Ingresar Nuevo Lote al Sistema")
            with st.form("nuevo_lote_form"):
                col1, col2 = st.columns(2)
                prod_id = col1.selectbox("Seleccionar Producto / Insumo:", df_p['id'].tolist(), format_func=lambda x: f"{df_p[df_p['id']==x]['codigo_au'].values[0]} - {df_p[df_p['id']==x]['nombre_au'].values[0]}")
                num_lote = col2.text_input("Número de Lote (ej: LOT-2026-001):")
                f_venc = col1.date_input("Fecha de Vencimiento:")
                cant_ini = col2.number_input("Cantidad Recibida:", min_value=0.1)
                
                if st.form_submit_button("Ingresar Lote y Generar Kardex"):
                    res_l = supabase.table("lotes").insert({
                        "producto_id": prod_id,
                        "numero_lote": num_lote,
                        "fecha_vencimiento": str(f_venc),
                        "cantidad_inicial": cant_ini,
                        "cantidad_actual": cant_ini
                    }).execute()
                    
                    lote_creado_id = res_l.data[0]['id']
                    registrar_kardex(prod_id, lote_creado_id, "ENTRADA", cant_ini, st.session_state['username'], f"Ingreso inicial de lote {num_lote}")
                    st.success(f"✅ Lote '{num_lote}' guardado exitosamente.")

            st.markdown("---")
            st.subheader("📦 Consultar Inventario por Lotes")
            res_stock = supabase.table("lotes").select("id, numero_lote, fecha_vencimiento, cantidad_inicial, cantidad_actual, productos(nombre_au, codigo_au, unidad_medida)").execute()
            if res_stock.data:
                flat_data = []
                for item in res_stock.data:
                    flat_data.append({
                        "ID Lote": item['id'],
                        "Código AU": item['productos']['codigo_au'],
                        "Producto": item['productos']['nombre_au'],
                        "N° Lote": item['numero_lote'],
                        "Vencimiento": item['fecha_vencimiento'],
                        "Stock Actual": item['cantidad_actual'],
                        "U.M.": item['productos']['unidad_medida']
                    })
                st.dataframe(pd.DataFrame(flat_data), use_container_width=True)

    # ==========================================
    # MÓDULO 4: PLANIFICACIÓN Y MRP
    # ==========================================
    elif menu == "🏭 Planificación y Producción (MRP)":
        st.title("🏭 Simulador de Planificación de Materiales (MRP)")
        st.info("Módulo para verificar disponibilidad de stock contra requerimientos de producción.")
        
        res_p = supabase.table("productos").select("id, nombre_au, codigo_au, stock_seguridad, unidad_medida").execute()
        if res_p.data:
            df_p = pd.DataFrame(res_p.data)
            st.dataframe(df_p, use_container_width=True)
        else:
            st.info("No hay datos cargados para realizar planificación MRP.")

    # ==========================================
    # MÓDULO 5: ÓRDENES DE COMPRA Y PDF
    # ==========================================
    elif menu == "📑 Órdenes de Compra y Generación PDF":
        st.title("📑 Emisión de Órdenes de Compra Multimoneda")
        res_p = supabase.table("productos").select("id, codigo_au, codigo_proveedor, nombre_au, nombre_proveedor, proveedor, unidad_medida").execute()
        
        if not res_p.data:
            st.warning("⚠️ Primero cree materias primas en el Maestro de Productos.")
        else:
            df_prods = pd.DataFrame(res_p.data)
            
            with st.form("form_oc"):
                st.subheader("Crear Nueva Orden de Compra")
                num_oc = st.text_input("Número Consecutivo de OC (ej: OC-2026-001):")
                prod_oc_id = st.selectbox("Seleccionar Insumo a Comprar:", df_prods['id'].tolist(), format_func=lambda x: f"{df_prods[df_prods['id']==x]['nombre_au'].values[0]} | Prov: {df_prods[df_prods['id']==x]['proveedor'].values[0]}")
                
                prod_info = df_prods[df_prods['id']==prod_oc_id].iloc[0]
                
                col_a, col_b, col_c = st.columns(3)
                cant_oc = col_a.number_input(f"Cantidad a Ordenar ({prod_info['unidad_medida']}):", min_value=0.1)
                moneda_oc = col_b.selectbox("Moneda Negociada:", ["COP", "USD", "EUR"])
                trm_oc = col_c.number_input("TRM Proyectada (COP):", value=4100.0 if moneda_oc != "COP" else 1.0)
                
                costo_unit_ext = st.number_input(f"Precio Unitario ({moneda_oc}):", min_value=0.0)
                
                btn_oc = st.form_submit_button("Generar y Registrar Orden de Compra")

            if btn_oc:
                fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                res_oc = supabase.table("ordenes_compra").insert({
                    "numero_oc": num_oc,
                    "proveedor": str(prod_info['proveedor']),
                    "estado": "ABIERTA",
                    "fecha_creacion": fecha_hoy
                }).execute()
                
                st.success(f"✅ Orden de Compra {num_oc} creada exitosamente.")
                
                pdf_bytes = generar_pdf_oc(num_oc, prod_info['proveedor'], prod_info['nombre_au'], prod_info['codigo_proveedor'], cant_oc, prod_info['unidad_medida'], costo_unit_ext, moneda_oc, trm_oc, fecha_hoy)
                
                st.download_button(
                    label="📥 Descargar Documento Oficial en PDF",
                    data=pdf_bytes,
                    file_name=f"Orden_de_Compra_{num_oc}_AURANZA.pdf",
                    mime="application/pdf"
                )

    # ==========================================
    # MÓDULO 6: HISTORIAL KARDEX
    # ==========================================
    elif menu == "📜 Historial Kardex de Movimientos":
        st.title("📜 Trazabilidad General - Kardex")
        res_k = supabase.table("kardex").select("id, fecha, tipo_movimiento, cantidad, usuario, observacion, productos(nombre_au, codigo_au), lotes(numero_lote)").execute()
        
        if res_k.data:
            flat_k = []
            for k in res_k.data:
                flat_k.append({
                    "Fecha / Hora": k['fecha'],
                    "Producto": k['productos']['nombre_au'] if k.get('productos') else 'N/A',
                    "Lote": k['lotes']['numero_lote'] if k.get('lotes') else 'N/A',
                    "Tipo Movimiento": k['tipo_movimiento'],
                    "Cantidad": k['cantidad'],
                    "Responsable": k['usuario'],
                    "Observación": k['observacion']
                })
            st.dataframe(pd.DataFrame(flat_k), use_container_width=True)
        else:
            st.info("Sin registros en el Kardex actualmente.")

    # ==========================================
    # MÓDULO 7: ADMINISTRACIÓN DE USUARIOS
    # ==========================================
    elif menu == "👥 Administración de Usuarios":
        st.title("👥 Control de Accesos y Usuarios")
        
        if st.session_state['rol'] != 'Administrador':
            st.warning("⚠️ Módulo restringido únicamente para el Administrador del sistema.")
        else:
            st.subheader("Registrar Nuevo Usuario")
            with st.form("nuevo_user_form"):
                col1, col2 = st.columns(2)
                nuevo_u = col1.text_input("Usuario Acceso:")
                nuevo_p = col2.text_input("Contraseña:", type="password")
                nuevo_r = col1.selectbox("Rol Asignado:", ["Administrador", "Compras", "Inventario", "Producción"])
                
                if st.form_submit_button("Crear Nuevo Usuario"):
                    h_pass = make_hashes(nuevo_p)
                    supabase.table("usuarios").insert({
                        "username": nuevo_u,
                        "password": h_pass,
                        "rol": nuevo_r
                    }).execute()
                    st.success(f"✅ Usuario {nuevo_u} registrado exitosamente.")
            
            st.markdown("---")
            st.subheader("Usuarios Activos")
            res_u = supabase.table("usuarios").select("id, username, rol").execute()
            if res_u.data:
                st.dataframe(pd.DataFrame(res_u.data), use_container_width=True)

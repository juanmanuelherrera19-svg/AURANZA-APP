import psycopg2
import psycopg2.extras
import streamlit as st

def get_connection():
    """Crea una conexión individual a Supabase."""
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        port=st.secrets["postgres"]["port"],
        dbname=st.secrets["postgres"]["dbname"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        cursor_factory=psycopg2.extras.DictCursor
    )

def guardar_kit(cod_kit, nombre_kit, costo_kit, precio_venta, rentabilidad, componentes):
    """
    Guarda un nuevo Kit y sus componentes ajustado estrictamente al esquema de la BD.
    """
    conn = get_connection()
    c = conn.cursor()
    try:
        # 1. Insertar la cabecera del Kit respetando las columnas exactas de la tabla kits
        c.execute("""
            INSERT INTO kits (codigo_kit, nombre_kit, precio_venta)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (cod_kit, nombre_kit, precio_venta))
        
        kit_row = c.fetchone()
        kit_id = kit_row['id']

        # 2. Insertar componentes válidos en kit_componentes
        for comp in componentes:
            if comp['codigo'] and comp['cantidad'] > 0:
                c.execute("""
                    INSERT INTO kit_componentes (kit_id, componente_id, porcentaje_o_cantidad)
                    VALUES (%s, %s, %s)
                """, (kit_id, comp['codigo'], comp['cantidad']))
            
        conn.commit()
        return True, "✅ Fórmula del Kit guardada exitosamente."
        
    except psycopg2.IntegrityError:
        conn.rollback()
        return False, f"❌ El código de Kit '{cod_kit}' ya existe en la base de datos. Utilice un número diferente."
    except Exception as e:
        conn.rollback()
        return False, f"❌ Error transaccional en la BD: {str(e)}"
        
    finally:
        c.close()
        conn.close()
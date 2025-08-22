import streamlit as st
from functions.management import Management
import pandas as pd

st.set_page_config(page_title="Automated configs", layout="centered")

# Estado incial:

ss = st.session_state
ss.setdefault("logged_in", False)
ss.setdefault("manage", None)                # Sesión/cliente ya autenticado
ss.setdefault("configs", [])                 # lista completa de configuraciones
ss.setdefault("origin", None)                # Selección actual de origen (1 único)
ss.setdefault("destinations", [])            # Selección actual de destinos (>1)
ss.setdefault("origin_tariff", None)
ss.setdefault("last_origin_checked", None)
ss.setdefault("login_password", None)

ss.setdefault("tariff_by_config", {})        # { "cfg_name": "2.0TD", ... }
ss.setdefault("last_updated_by_config", {})  # { cfg: "YYYY-MM-DD ..." }
ss.setdefault("last_filtered_origin", None)  # para no recalcular en cada rerun
ss.setdefault("incompatible_cfgs", [])       # para mostrar cuáles quedaron fuera
ss.setdefault("data_config", {})             # Datos de la configuración origen a replicar
ss.setdefault("apply_mode", False)           # Tras pulsar "Aplicar selección"
ss.setdefault("last_replication_summary", None) # {updated: [], failed: [], total: int}

# st.subheader("Réplica de configuraciones en App: Gestión Energética")

if not ss.logged_in:
    with st.form("login", clear_on_submit=False):
        user = st.text_input("Usuario", key="login_user")
        pswd = st.text_input("Contraseña", type="password", key="login_password")
        ok = st.form_submit_button("Entrar")
    if ok:
        if not user or not pswd:
            st.warning("Debes ingresar las credenciales de acceso a la plataforma")
            st.stop()
        try:
            with st.spinner("Accediendo a la plataforma y cargando configuraciones..."):
                manage = Management(user, pswd)
                # Hacemos un login explícito ya que ahora no cerramos el browser
                if not manage.login():
                    raise RuntimeError("Login fallido")

                cfgs = manage.get_config_list()
                ss.manage = manage
                ss.configs = sorted({str(c) for c in cfgs})
                ss.logged_in = True

            # Clear and rerun the password
            ss.pop("login_password", None)

        except Exception as e:
            st.error("El usuario o la contraseña son incorrectos, o hubo un problema al conectar.")
            with st.expander("Más detalles..."):
                st.exception(e)
            st.stop()


# ------------ UI PRINCIPAL ------------
if ss.logged_in:

    if ss.get("last_replication_summary"):
        res = ss.last_replication_summary
        ok = len(res.get("updated", []))
        total = res.get("total", 0)
        failed = res.get("failed", [])

        if ok == total:
            st.success(f"✅ Proceso de réplica completado con éxito en {ok}/{total} destinos.")
        elif ok > 0:
            st.warning(
                f"Réplica completada con incidencias: {ok}/{total} destinos OK. Fallaron: {', '.join(failed) or '—'}")
        else:
            st.error("La réplica no se pudo completar en ningún destino.")

        # Limpiar para que no se repita en el siguiente run:
        ss.last_replication_summary = None

    st.success("Autenticación correcta y configuraciones cargadas")
    st.subheader("Selecciona la configuración de origen y las de destino")

    if not ss.configs:
        st.info("No hay configuraciones disponibles en la plataforma.")
        st.stop()

    # Si la selección previa de origen ya no existe (p. ej. tras refrescar lista), la limpiamos
    if ss.origin not in ss.configs:
        ss.origin = None

    # ------------ CONFIGURACIÓN ORIGEN ------------

    col1, col2 = st.columns(2, gap="large")

    with col1:
        # Selectbox de origen (único)
        opts_origen = ["— Selecciona —"] + ss.configs
        idx = opts_origen.index(ss.origin) if ss.origin in ss.configs else 0
        chosen = st.selectbox("Configuración origen (única)", options=opts_origen, index=idx)

        new_origin = None if chosen == "— Selecciona —" else chosen
        if new_origin != ss.origin:
            # reset de estados dependientes del origen
            ss.origin = new_origin
            ss.origin_tariff = None
            ss.origin_last_updated = None
            ss.last_origin_checked = None
            ss.last_filtered_origin = None
            ss.incompatible_cfgs = []
            ss.destinations = []
            ss.apply_mode = False
            ss.data_config = {}

        # Detectar tarifa del origen (una sola vez por cambio):
        if ss.origin and ss.origin != ss.last_origin_checked:
            try:
                with st.spinner("Determinando el tipo de tarifa de la configuración origen..."):
                    ss.manage.ensure_session()
                    origin_last_updated, ss.data_config, ss.origin_tariff = ss.manage.detect_config(
                        ss.origin, origin=True
                    )
                    ss.origin_last_updated = (origin_last_updated or "")
                    ss.last_updated_by_config[ss.origin] = ss.origin_last_updated
                    ss.tariff_by_config[ss.origin] = ss.origin_tariff
                    ss.last_origin_checked = ss.origin
            except Exception as e:
                st.error("No se pudo determinar la tarifa de la configuración origen")
                with st.expander("Más detalles..."):
                    st.exception(e)

        if ss.origin_tariff:
            st.info(
                f"**Origen:** {ss.origin}\n\n"
                f"• Tarifa: **{ss.origin_tariff}**\n\n"
                f"• Última actualización: **{ss.origin_last_updated or '—'}**"
            )

    # --- DESTINOS (filtrados por tarifa del origen) ---

    with col2:
        # Si hemos detectado la tarifa origen pero aún no hemos filtrado por este tipo de tarifa:
        if ss.origin and ss.origin_tariff and ss.last_filtered_origin != ss.origin:
            try:
                with st.spinner("Filtrando destinos por tipo de tarifa..."):
                    ss.manage.ensure_session()
                    origin_tariff = ss.origin_tariff
                    origin_last_updated = ss.origin_last_updated
                    # Calculamos la tarifa para cada config si aún no está cacheada:
                    pending = [c for c in ss.configs if c not in ss.tariff_by_config]
                    total = len(pending)
                    if total:
                        prog = st.progress(0.0, text="Calculando tarifas...")
                        for i, cfg in enumerate(pending, start=1):
                            try:
                                if cfg == ss.origin:
                                    ss.tariff_by_config[cfg] = origin_tariff
                                    ss.last_updated_by_config[cfg] = origin_last_updated
                                else:
                                    ss.last_updated_by_config[cfg], ss.tariff_by_config[cfg] = ss.manage.detect_config(cfg)
                            except Exception:
                                ss.tariff_by_config[cfg] = None
                            prog.progress(i/total)
                        prog.empty()

                    # Construimos las opciones compatibles:
                    compatible = [
                        c for c in ss.configs
                        if c != ss.origin and ss.tariff_by_config.get(c) == origin_tariff
                    ]

                    ss.incompatible_cfgs = [
                        c for c in ss.configs
                        if c != ss.origin and ss.tariff_by_config.get(c) not in (origin_tariff, None)
                    ]

                    ss.destinations = [d for d in ss.destinations if d in compatible]
                    ss.last_filtered_origin = ss.origin

            except Exception as e:
                st.error("Ocurrió un problema al filtrar los destinos")
                with st.expander("Más detalles..."):
                    st.exception(e)

        # Opciones destino con la misma tarifa que la configuración origen:
        if ss.origin and ss.origin_tariff:
            dest_options = [
                c for c in ss.configs
                if c != ss.origin and ss.tariff_by_config.get(c) == ss.origin_tariff
            ]

        else:
            dest_options = []

        # Etiquetamos con iconos para identificar las configuraciones actualizadas de las que no:
        def dest_label(name: str) -> str:
            lu = ss.last_updated_by_config.get(name)
            o = (ss.origin_last_updated or "").strip()
            if lu is None:
                icon, tag = "❓", "sin info"
            elif o and (lu.strip() == o):
                icon, tag = "✅", "actualizada"
            else:
                icon, tag = "⚠️", "pendiente"

            return f"{icon} {name} - {lu or '--'} ({tag})"


        # Multiselect de destinos (>=1), sin el origen
        ss.destinations = st.multiselect(
            "Configuraciones destino (mínimo 1, misma tarifa que configuración origen)",
            options=dest_options,
            default=ss.destinations,
            disabled=not (ss.origin and ss.origin_tariff), # Lo bloqueamos hasta escoger origen y determinar su tarifa
            key="destinations_multiselect",
            help="Selecciona primero la configuración origen, luego podrás escoger entre las configuraciones destino compatibles",
            format_func=dest_label
        )

        # Leyenda
        st.caption("✅ actualizada | ⚠️ pendiente  | ❓ sin info")

    # Vista rápida de lo elegido con la clasificación de configuraciones en función del tipo de tarifa:
    st.markdown("### Resumen")
    st.write(
        {
            "Origen": ss.origin if ss.origin else "—",
            "Tarifa origen": ss.origin_tariff if ss.origin_tariff else "-",
            "Destinos": ss.destinations if ss.destinations else []
        }
    )

    # Botonera
    colA, colB, colC = st.columns(3)
    with colA:
        # Validación: requiere origen y >=1 destino
        valid = (ss.origin is not None) and (len(ss.destinations) >= 1)
        apply_clicked = st.button("Aplicar selección", type="primary", disabled=not valid)
        if apply_clicked and valid:
            ss.apply_mode = True
        if not valid:
            st.caption("Selecciona 1 origen y al menos 1 destino para continuar.")

    with colB:
        if st.button("Limpiar selección"):
            # Limpiamos estados sin cerrar sesión:
            try:
                for k in [
                    "origin", "destinations", "origin_tariff", "origin_last_updated",
                    "last_origin_checked", "last_filtered_origin", "incompatible_cfgs",
                    "data_config", "apply_mode"
                ]:
                    ss[k] = None if k.endswith("_last_updated") or k.endswith("_tariff") else []

                ss["data_config"] = {}
                ss["apply_mode"] = False

            finally:
                st.rerun()

    with colC:
        if st.button("Cerrar sesión"):
            try:
                with st.spinner("Cerrando sesión del navegador..."):
                    ss.manage.close(hard=True)
            finally:
                for k in [
                    "manage", "logged_in", "configs", "origin", "destinations",
                    "origin_tariff", "origin_last_updated", "last_origin_checked",
                    "last_filtered_origin", "login_password", "tariff_by_config",
                    "last_updated_by_config", "incompatible_cfgs", "data_config", "apply_mode"
                ]:
                    ss.pop(k, None)

                st.rerun()

    # ----- UNA VEZ HEMOS SELECCIONADO ORIGEN Y DESTINOS Y APLICADO LOS CAMBIOS -----

    if ss.get("apply_mode") and valid:
        st.markdown("### Datos de la configuración origen")
        try:
            df = pd.DataFrame(ss.data_config)
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error("No se pudo construir el DataFrame de la configuración origen.")
            with st.expander("Más detalles..."):
                st.exception(e)

        st.markdown("### Réplica")
        start = st.button("Comenzar réplica", type="primary")
        if start:
            # Progreso por destino
            total = len(ss.destinations)
            prog = st.progress(0.0, text="Iniciando réplica...")
            updated, failed = [], []

            for i, dst in enumerate(ss.destinations, start=1):
                try:
                    with st.spinner(f"Replicando en: {dst} ({i}/{total})..."):
                        try:
                            new_lu = ss.manage.replicate_to(dst, ss.data_config, ss.origin_last_updated)
                        except TypeError:
                            new_lu = None

                        # Refrescamos la caché para que el icono cambie en el próximo rerun():
                        ss.last_updated_by_config[dst] = (new_lu or ss.origin_last_updated or "")
                        updated.append(dst)

                except Exception as e:
                    st.error(f"Fallo al replicar en **{dst}**")
                    with st.expander(f"Detalles ({dst})"):
                        st.exception(e)
                finally:
                    prog.progress(i / total)

            prog.empty()

            # Guardamos el resumen y salimos de apply_mode:
            ss.last_replication_summary = {"updated": updated, "failed": failed, "total": total}
            ss.apply_mode = False

            # Forzamos el rerender para que:
            # - se vea el mensaje (lo mostramos al inicio del próximo run)
            # - el multiselect se re renderice con los iconos actualizados

            st.rerun()










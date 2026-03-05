# app.py
# -*- coding: utf-8 -*-

import io
import re
import os
import json
import streamlit as st
from datetime import datetime
from openpyxl import load_workbook, Workbook

from pdf_engine import build_pdf_bytes_mixed

st.set_page_config(page_title="Gerador de Tags", layout="wide")

# =========================
# CONFIG (arquivos locais)
# =========================
ALLOWLIST_FILE = "users_allowlist.json"
BASE_CACHE_FILE = "bases_cache.json"  # cache local das bases (JSON)

# =========================
# AUTH (simples)
# =========================
ADMIN_USER = "admin"
ADMIN_PASS = "cpcm123"

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def norm_user(s: str) -> str:
    return (s or "").strip().upper()

def user_password_rule(username: str) -> str:
    # senha do usuário normal = <usuario>123 (case-insensitive)
    u = (username or "").strip().lower()
    return f"{u}123"

# =========================
# Helpers de TAG / XLSX
# =========================
def norm_tag(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("_", "-")
    s = re.sub(r"\s+", "", s)
    return s.upper()

def get_prefix(tag: str) -> str:
    m = re.match(r"^([A-Z]+)", (tag or "").upper())
    return m.group(1) if m else ""

def idx_of(headers_list, *names):
    for n in names:
        n = n.upper()
        if n in headers_list:
            return headers_list.index(n)
    return None

def list_sheets(uploaded_file):
    if uploaded_file is None:
        return []
    bio = io.BytesIO(uploaded_file.getvalue())
    wb = load_workbook(bio, read_only=True, data_only=True)
    names = list(wb.sheetnames)
    wb.close()
    return names

def read_xlsx(uploaded_file, sheet_name=None):
    if uploaded_file is None:
        return [], []
    bio = io.BytesIO(uploaded_file.getvalue())
    wb = load_workbook(bio, read_only=True, data_only=True)
    ws = wb[sheet_name] if (sheet_name and sheet_name in wb.sheetnames) else wb.active
    it = ws.iter_rows(values_only=True)
    header = next(it, None)
    if not header:
        wb.close()
        return [], []
    headers = [str(h).strip().upper() if h is not None else "" for h in header]
    rows = list(it)
    wb.close()
    return headers, rows

# =========================
# REGRA DO SUPERVISÓRIO (PARÊNTESES OBRIGATÓRIO)
# =========================
def _fix_parentheses(s: str) -> str:
    """
    Corrige parênteses desbalanceados mantendo parênteses internos.
    - Ignora ')' sobrando antes de qualquer '('
    - Fecha todos os '(' abertos no final
    """
    s = (s or "").strip()
    if not s:
        return s

    cleaned = []
    open_count = 0
    for ch in s:
        if ch == "(":
            open_count += 1
            cleaned.append(ch)
        elif ch == ")":
            if open_count > 0:
                open_count -= 1
                cleaned.append(ch)
        else:
            cleaned.append(ch)

    s = "".join(cleaned)
    if open_count > 0:
        s = s + (")" * open_count)
    return s

def normalize_supervisor_field(text: str) -> str:
    """
    Garante UM par de parênteses externos obrigatório:
    - Se já tiver ( ... ), não duplica
    - Se faltar abrir/fechar, corrige
    - Mantém parênteses internos (ex: (P-410))
    """
    s = (text or "").strip().upper()
    s = _fix_parentheses(s)

    # se já tiver par externo, remove pra reconstruir sem duplicar
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()

    s = _fix_parentheses(s)
    return f"({s})" if s else "()"

def clean_prefix_desc(prefix_desc: str) -> str:
    """
    Prefixo da base pode vir com "(" no final.
    Remove lixo final pra ficar: "MOTOR ELETRICO" / "TRANSMISSOR ...", etc.
    """
    s = (prefix_desc or "").strip().upper()
    s = re.sub(r"\(\s*$", "", s).strip()
    s = re.sub(r"[\-:]\s*$", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def build_manual_description(prefix_desc: str, supervisor_text: str) -> str:
    """
    Monta: PREFIX_DESC + (SUPERVISÓRIO corrigido)
    Ex: MOTOR ELETRICO + BOMBA (P-410  -> MOTOR ELETRICO (BOMBA (P-410))
    """
    p = clean_prefix_desc(prefix_desc)
    sup = normalize_supervisor_field(supervisor_text)
    return f"{p} {sup}".strip() if p else sup

def remove_tag_prefix_inside_parentheses(tag: str, desc_final: str) -> str:
    """
    Remove (PREFIXO) caso apareça e seja igual ao prefixo da TAG.
    Ex: "MOTOR ELETRICO (ME) (BOMBA...)" -> "MOTOR ELETRICO (BOMBA...)"
    """
    t = (tag or "").strip().upper()
    d = (desc_final or "").strip().upper()
    pfx = get_prefix(t)
    if not pfx:
        return d
    d = re.sub(rf"\(\s*{re.escape(pfx)}\s*\)", " ", d)
    d = re.sub(r"\s+", " ", d).strip()
    return d

# =========================
# Persistência simples (JSON)
# =========================
def load_allowlist():
    if os.path.exists(ALLOWLIST_FILE):
        try:
            with open(ALLOWLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return sorted({norm_user(x) for x in data if str(x).strip()})
        except Exception:
            pass
    return []

def save_allowlist(users):
    users = sorted({norm_user(x) for x in (users or []) if str(x).strip()})
    with open(ALLOWLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    return users

def save_bases_cache(base_tags, base_prefix):
    data = {"base_tags": base_tags, "base_prefix": base_prefix, "saved_at": now_str()}
    with open(BASE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def load_bases_cache():
    if os.path.exists(BASE_CACHE_FILE):
        try:
            with open(BASE_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            bt = data.get("base_tags") or {}
            bp = data.get("base_prefix") or {}
            if isinstance(bt, dict) and isinstance(bp, dict):
                return bt, bp, data.get("saved_at", "")
        except Exception:
            pass
    return {}, {}, ""

# =========================
# Session State
# =========================
def ensure_state():
    if "auth" not in st.session_state:
        st.session_state["auth"] = {"logged": False, "role": "", "user": ""}

    # LISTA POR USUÁRIO
    if "items_by_user" not in st.session_state:
        st.session_state["items_by_user"] = {}  # user -> list[dict]

    if "allowlist" not in st.session_state:
        st.session_state["allowlist"] = load_allowlist()

    if "base_tags" not in st.session_state or "base_prefix" not in st.session_state:
        bt, bp, saved_at = load_bases_cache()
        st.session_state["base_tags"] = bt
        st.session_state["base_prefix"] = bp
        st.session_state["bases_saved_at"] = saved_at

    # RELATÓRIO POR USUÁRIO (último PDF gerado por cada user)
    if "report_by_user" not in st.session_state:
        st.session_state["report_by_user"] = {}  # user -> {bytes,name,meta}

ensure_state()

def get_user_items(user: str):
    m = st.session_state["items_by_user"]
    if user not in m:
        m[user] = []
    return m[user]

def set_user_items(user: str, items):
    st.session_state["items_by_user"][user] = items

# =========================
# LOGIN SCREEN
# =========================
st.title("Gerador de Tags")

auth = st.session_state["auth"]

if not auth["logged"]:
    st.subheader("Login")

    u_in = st.text_input("Usuário", value="", placeholder="ex: inpasa")
    p_in = st.text_input("Senha", value="", type="password", placeholder="ex: inpasa")

    do_login = st.button("Entrar")

    if do_login:
        u = (u_in or "").strip()
        p = (p_in or "").strip()

        if not u or not p:
            st.error("Informe usuário e senha.")
            st.stop()

        # admin
        if u.lower() == ADMIN_USER and p == ADMIN_PASS:
            st.session_state["auth"] = {"logged": True, "role": "admin", "user": "ADMIN"}
            st.rerun()

        # user comum
        if p.lower() == user_password_rule(u).lower():
            user_norm = norm_user(u)
            allow = st.session_state["allowlist"]
            if allow and (user_norm not in allow):
                st.error("Usuário não autorizado. Fale com o administrador.")
                st.stop()

            st.session_state["auth"] = {"logged": True, "role": "user", "user": user_norm}
            st.rerun()

        st.error("Usuário ou senha inválidos.")

    st.stop()

# =========================
# AUTH OK
# =========================
role = auth["role"]
user = auth["user"]
is_admin = (role == "admin")

topcol1, topcol2 = st.columns([3, 1])
with topcol1:
    st.caption(f"Logado como: **{user}**  | Perfil: **{role.upper()}**")
with topcol2:
    if st.button("Sair"):
        st.session_state["auth"] = {"logged": False, "role": "", "user": ""}
        st.rerun()

# =========================
# ADMIN PANEL
# =========================
if is_admin:
    with st.expander("🔒 Admin — Bases + Usuários + Relatórios", expanded=False):
        st.markdown("### Bases (somente admin)")
        colA, colB = st.columns([1, 1], gap="large")

        with colA:
            up_base = st.file_uploader(
                "Base principal (XLSX) colunas: TAG, DESCRIÇÃO/DESCRICAO",
                type=["xlsx"],
                key="up_base"
            )
            base_sheets = list_sheets(up_base)
            base_sheet = st.selectbox("Aba da Base principal", options=base_sheets or ["(envie o arquivo)"], index=0)

        with colB:
            up_prefix = st.file_uploader(
                "Base de prefixos (XLSX) colunas: PREFIXO, PRE_DESCRIÇÃO",
                type=["xlsx"],
                key="up_prefix"
            )
            pref_sheets = list_sheets(up_prefix)
            pref_sheet = st.selectbox("Aba da Base prefixos", options=pref_sheets or ["(envie o arquivo)"], index=0)

        if st.button("Salvar bases"):
            base_tags = {}
            base_prefix = {}

            headers, rows = read_xlsx(up_base, base_sheet if base_sheets else None)
            if not headers:
                st.error("Envie a base principal.")
                st.stop()

            i_tag = idx_of(headers, "TAG")
            i_desc = idx_of(headers, "DESCRIÇÃO", "DESCRICAO")
            if i_tag is None or i_desc is None:
                st.error("Base principal inválida: precisa de TAG e DESCRIÇÃO/DESCRICAO na linha 1.")
                st.stop()

            for r in rows:
                t = norm_tag(str(r[i_tag]) if i_tag < len(r) and r[i_tag] is not None else "")
                d = str(r[i_desc]).strip() if i_desc < len(r) and r[i_desc] is not None else ""
                if t:
                    base_tags[t] = d.upper().strip()

            headersp, rowsp = read_xlsx(up_prefix, pref_sheet if pref_sheets else None)
            if headersp:
                i_pfx = idx_of(headersp, "PREFIXO")
                i_pd = idx_of(headersp, "PRE_DESCRIÇÃO", "PRE_DESCRICAO", "PRÉ_DESCRIÇÃO", "PRE-DESCRICAO")
                if i_pfx is None or i_pd is None:
                    st.error("Base prefixos inválida: precisa de PREFIXO e PRE_DESCRIÇÃO na linha 1.")
                    st.stop()

                for r in rowsp:
                    p = (str(r[i_pfx]).strip().upper() if i_pfx < len(r) and r[i_pfx] is not None else "")
                    pdsc = (str(r[i_pd]).strip() if i_pd < len(r) and r[i_pd] is not None else "")
                    if p:
                        base_prefix[p] = pdsc.upper().strip()

            st.session_state["base_tags"] = base_tags
            st.session_state["base_prefix"] = base_prefix
            st.session_state["bases_saved_at"] = now_str()
            save_bases_cache(base_tags, base_prefix)
            st.success(f"Bases salvas: {len(base_tags)} TAGs | {len(base_prefix)} prefixos")

        st.caption(
            f"Cache atual: {len(st.session_state['base_tags'])} TAGs | "
            f"{len(st.session_state['base_prefix'])} prefixos | "
            f"salvo em: {st.session_state.get('bases_saved_at') or '—'}"
        )

        st.divider()
        st.markdown("### Usuários permitidos (allowlist)")
        current = st.session_state["allowlist"]
        txt = st.text_area("1 usuário por linha", value="\n".join(current), height=160)
        if st.button("Salvar allowlist"):
            users = [line.strip() for line in txt.splitlines() if line.strip()]
            st.session_state["allowlist"] = save_allowlist(users)
            st.success(f"Allowlist salva ({len(st.session_state['allowlist'])} usuários).")

        st.divider()
        st.markdown("### Relatórios XLSX (somente admin)")
        rep_map = st.session_state["report_by_user"]
        rep_users = sorted(rep_map.keys())
        if rep_users:
            sel = st.selectbox("Escolha o usuário do relatório", options=rep_users, index=0)
            rep = rep_map.get(sel) or {}
            st.download_button(
                "Baixar relatório do último PDF deste usuário",
                data=rep.get("bytes", b""),
                file_name=rep.get("name", f"relatorio_{sel}.xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            meta = rep.get("meta") or {}
            st.caption(f"Gerado em: {meta.get('ts','—')} | por: {meta.get('user','—')} | itens: {meta.get('count','—')}")
        else:
            st.info("Nenhum relatório gerado ainda.")

st.divider()

# =========================
# USER FLOW
# =========================
st.subheader("2) Inserir TAG")

base_tags = st.session_state["base_tags"]
base_prefix = st.session_state["base_prefix"]

tag_raw = st.text_input("TAG", value="", placeholder="Ex: INC-1608516A / TIT-1800100 / ME-1203019")
tag = norm_tag(tag_raw)

is_big = st.checkbox("TAG GRANDE (150×150)", value=False)
layout_name = "big" if is_big else "small"

desc_in = ""
manual_flag = False
base_desc = ""

if tag:
    base_desc = base_tags.get(tag, "")

    if base_desc:
        st.info("TAG encontrada na base.")
        alter = st.checkbox("Alterar descrição desta TAG", value=False)
        desc_in = st.text_input("Descrição", value=base_desc, disabled=(not alter))
        desc_in = (desc_in or "").strip().upper()
        manual_flag = False
    else:
        st.warning("TAG NÃO encontrada na base.")
        prefix = get_prefix(tag)
        pre_desc = base_prefix.get(prefix, "")
        st.caption(f"Sugestão por prefixo ({prefix}): {pre_desc or '—'}")

        sup = st.text_input(
            "Descrição do supervisório / IO List",
            value="",
            placeholder="Ex: BOMBA DE TESTE (P-410) ou (BOMBA DE TESTE (P-410"
        )

        desc_final = build_manual_description(pre_desc, sup)
        desc_in = remove_tag_prefix_inside_parentheses(tag, desc_final)
        manual_flag = True

if st.button("Adicionar à lista"):
    if not tag:
        st.error("Informe a TAG.")
    elif not desc_in.strip():
        st.error("Informe a descrição.")
    else:
        items = get_user_items(user)
        now = now_str()
        changed = bool(base_desc and (desc_in.strip().upper() != base_desc.strip().upper()))

        updated = False
        for it in items:
            if it["tag"] == tag:
                it.update({
                    "desc": desc_in.strip().upper(),
                    "layout": layout_name,
                    "manual": bool(manual_flag),
                    "changed": bool(changed),
                    "base_desc": base_desc.strip().upper(),
                    "updated_at": now,
                    "updated_by": user,
                })
                updated = True
                break

        if not updated:
            items.append({
                "tag": tag,
                "desc": desc_in.strip().upper(),
                "layout": layout_name,
                "manual": bool(manual_flag),
                "changed": bool(changed),
                "base_desc": base_desc.strip().upper(),
                "created_at": now,
                "created_by": user,
                "updated_at": now,
                "updated_by": user,
            })

        set_user_items(user, items)
        st.success("Adicionado/atualizado.")

st.divider()

# =========================
# STEP 3 (somente limpar + pdf) — POR USUÁRIO
# =========================
st.subheader("3) Lista atual")

items = get_user_items(user)

if items:
    st.dataframe(
        [
            {
                "TAG": it["tag"],
                "DESCRIÇÃO": it["desc"],
                "LAYOUT": "150×150" if it.get("layout") == "big" else "100×50",
                "MANUAL": "SIM" if it.get("manual") else "",
                "ALTERADO": "SIM" if it.get("changed") else "",
            }
            for it in items
        ],
        use_container_width=True,
        height=360
    )
else:
    st.write("Nenhuma TAG adicionada (na sua lista).")

c1, c2 = st.columns([1, 1])

with c1:
    if st.button("Limpar lista"):
        set_user_items(user, [])
        st.success("Sua lista foi limpa.")

with c2:
    if items:
        pdf_bytes = build_pdf_bytes_mixed([
            (it["tag"], it["desc"], it.get("layout", "small"))
            for it in items
        ])

        # relatório do último PDF (salvo por usuário; admin baixa no painel)
        ts_pdf = now_str()
        wb = Workbook()
        ws = wb.active
        ws.title = "RELATORIO"
        ws.append(["DATA_HORA_PDF", "USUARIO_PDF", "TAG", "DESCRIÇÃO_FINAL", "LAYOUT", "STATUS", "DESCRIÇÃO_BASE"])

        for it in items:
            status = "MANUAL" if it.get("manual") else ("ALTERADO" if it.get("changed") else "OK")
            ws.append([
                ts_pdf,
                user,
                it["tag"],
                it["desc"],
                "150×150" if it.get("layout") == "big" else "100×50",
                status,
                it.get("base_desc", "") if it.get("base_desc") else "",
            ])

        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)

        rep_name = f"relatorio_tags_{user}_{ts_pdf.replace(':','-').replace(' ','_')}.xlsx"
        st.session_state["report_by_user"][user] = {
            "bytes": bio.getvalue(),
            "name": rep_name,
            "meta": {"ts": ts_pdf, "user": user, "count": len(items)}
        }

        st.download_button(
            "Gerar/baixar PDF",
            data=pdf_bytes,
            file_name="tags.pdf",
            mime="application/pdf"
        )
    else:
        st.button("Gerar/baixar PDF", disabled=True)


import os
import zipfile
import shutil
import hashlib
import tempfile
import subprocess
import base64
from io import BytesIO
from lxml import etree
from jinja2 import Template
import barcode
from barcode.writer import ImageWriter

# --- CONFIGURAÇÕES ---
BASE_DIR = r"C:\DANFE"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
os.makedirs(BASE_DIR, exist_ok=True)

def formatar_moeda(valor):
    if not valor: return "0,00"
    try:
        val = float(valor)
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

def formatar_quantidade(valor):
    if not valor: return "0,00"
    try:
        val = float(valor)
        # Se for inteiro, não mostra casas decimais excessivas
        if val.is_integer():
            return f"{int(val)}"
        return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return valor

def formatar_documento(doc):
    if not doc: return ""
    doc = ''.join(filter(str.isdigit, str(doc)))
    if len(doc) == 14: return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
    if len(doc) == 11: return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
    return doc

def formatar_cep(cep):
    if not cep: return ""
    c = ''.join(filter(str.isdigit, str(cep)))
    if len(c) == 8: return f"{c[:5]}-{c[5:]}"
    return c

def formatar_telefone(tel):
    if not tel: return ""
    t = ''.join(filter(str.isdigit, str(tel)))
    if len(t) == 10: return f"({t[:2]}) {t[2:6]}-{t[6:]}"
    if len(t) == 11: return f"({t[:2]}) {t[2:7]}-{t[7:]}"
    return t

def formatar_chave(chave):
    if not chave: return ""
    return " ".join([chave[i:i+4] for i in range(0, len(chave), 4)])

def gerar_codigo_barras_base64(chave):
    if not chave or len(chave) != 44:
        return ""
    from barcode import Code128
    from barcode.writer import ImageWriter
    
    options = {
        'module_width': 0.38,
        'module_height': 11.5,
        'quiet_zone': 2.7,
        'font_size': 0,
        'text_distance': 0,
        'background': 'white',
        'foreground': 'black',
        'write_text': False,
    }
    
    code = Code128(chave, writer=ImageWriter())
    buffer = BytesIO()
    code.write(buffer, options)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"

def xml_to_dict(xml_path):
    parser = etree.XMLParser(recover=True)
    root = etree.parse(xml_path, parser=parser).getroot()
    
    # Remove namespaces
    for elem in root.getiterator():
        if not hasattr(elem.tag, 'find'): continue
        i = elem.tag.find('}')
        if i >= 0: elem.tag = elem.tag[i+1:]

    def get(path, node=root):
        el = node.find(path)
        return el.text.strip() if el is not None and el.text else ""

    ide = root.find(".//ide")
    emit = root.find(".//emit")
    dest = root.find(".//dest")
    total = root.find(".//total/ICMSTot")
    infAdic = root.find(".//infAdic")
    infNFe = root.find(".//infNFe")
    transp = root.find(".//transp")
    
    chave_raw = infNFe.attrib.get('Id', '')[3:] if infNFe is not None else ""

    enderEmit = emit.find("enderEmit")
    enderDest = dest.find("enderDest") if dest is not None else None
    
    # Datas
    dhEmi = get("dhEmi", ide)
    dhSai = get("dhSaiEnt", ide)
    
    data_emi = dhEmi[:10].split('-')[::-1] if dhEmi else []
    data_sai = dhSai[:10].split('-')[::-1] if dhSai else []
    hora_sai = dhSai[11:19] if dhSai and len(dhSai) > 11 else ""

    # Endereço Emitente Formatado
    emit_end = ""
    if enderEmit is not None:
        emit_end = f"{get('xLgr', enderEmit)}, {get('nro', enderEmit)}"
        if get('xCpl', enderEmit): emit_end += f" {get('xCpl', enderEmit)}"
        emit_end += f" - {get('xBairro', enderEmit)}"
        emit_end += f" - {get('xMun', enderEmit)} - {get('UF', enderEmit)}"

    # Transportadora
    transporta = transp.find("transporta") if transp is not None else None
    vol = transp.find("vol") if transp is not None else None
    modFrete = get("modFrete", transp)
    desc_frete = "9 - Sem Frete"
    if modFrete == "0": desc_frete = "0 - Emitente"
    elif modFrete == "1": desc_frete = "1 - Destinatário"

    dados = {
        "chave": formatar_chave(chave_raw),
        "chave_raw": chave_raw,
        "barcode": gerar_codigo_barras_base64(chave_raw),
        
        "nat_op": get("natOp", ide),
        "modelo": get("mod", ide),
        "serie": get("serie", ide),
        "numero": get("nNF", ide),
        "tp_nf": get("tpNF", ide), 
        "dh_emi": "/".join(data_emi),
        "dh_sai": "/".join(data_sai),
        "h_sai": hora_sai,
        "prot_nfe": get(".//protNFe/infProt/nProt"),
        "dh_prot": get(".//protNFe/infProt/dhRecbto"),
        
        "emit_nome": get("xNome", emit),
        "emit_cnpj": formatar_documento(get("CNPJ", emit)),
        "emit_ie": get("IE", emit),
        "emit_ie_st": get("IEST", emit),
        "emit_ender_full": emit_end,
        "emit_cep": formatar_cep(get('CEP', enderEmit)),
        "emit_fone": formatar_telefone(get('fone', enderEmit)),
        
        "dest_nome": get("xNome", dest) if dest is not None else "CONSUMIDOR",
        "dest_cnpj": formatar_documento(get("CNPJ", dest) or get("CPF", dest)),
        "dest_ie": get("IE", dest) if dest is not None else "",
        "dest_lgr": f"{get('xLgr', enderDest)}, {get('nro', enderDest)}" if enderDest is not None else "",
        "dest_bairro": get("xBairro", enderDest) if enderDest is not None else "",
        "dest_mun": get("xMun", enderDest) if enderDest is not None else "",
        "dest_uf": get("UF", enderDest) if enderDest is not None else "",
        "dest_cep": formatar_cep(get("CEP", enderDest)) if enderDest is not None else "",
        "dest_fone": formatar_telefone(get("fone", enderDest)) if enderDest is not None else "",

        "v_bc": formatar_moeda(get("vBC", total)),
        "v_icms": formatar_moeda(get("vICMS", total)),
        "v_bc_st": formatar_moeda(get("vBCST", total)),
        "v_st": formatar_moeda(get("vST", total)),
        "v_prod": formatar_moeda(get("vProd", total)),
        "v_frete": formatar_moeda(get("vFrete", total)),
        "v_seg": formatar_moeda(get("vSeg", total)),
        "v_desc": formatar_moeda(get("vDesc", total)),
        "v_ipi": formatar_moeda(get("vIPI", total)),
        "v_outro": formatar_moeda(get("vOutro", total)),
        "v_nf": formatar_moeda(get("vNF", total)),

        # Transportador
        "transp_nome": get("xNome", transporta) if transporta is not None else "",
        "transp_cnpj": formatar_documento(get("CNPJ", transporta) or get("CPF", transporta)) if transporta is not None else "",
        "transp_ender": get("xEnder", transporta) if transporta is not None else "",
        "transp_mun": get("xMun", transporta) if transporta is not None else "",
        "transp_uf": get("UF", transporta) if transporta is not None else "",
        "transp_ie": get("IE", transporta) if transporta is not None else "",
        "transp_mod": desc_frete,
        "transp_qvol": get("qVol", vol) if vol is not None else "",
        "transp_esp": get("esp", vol) if vol is not None else "",
        "transp_peso_b": formatar_quantidade(get("pesoB", vol)) if vol is not None else "",
        "transp_peso_l": formatar_quantidade(get("pesoL", vol)) if vol is not None else "",

        "inf_cpl": get("infCpl", infAdic),
        "produtos": []
    }

    for det in root.findall(".//det"):
        prod = det.find("prod")
        imposto = det.find("imposto")
        
        v_icms = "0,00"
        bc_icms = "0,00"
        aliq_icms = "0,00"
        aliq_ipi = "0,00"
        v_ipi = "0,00"
        
        # Lógica simplificada de impostos
        if imposto is not None:
            for child in imposto:
                if "ICMS" in child.tag:
                    icms_tag = list(child)[0] if list(child) else None
                    if icms_tag is not None:
                        v_icms = formatar_moeda(get("vICMS", icms_tag))
                        bc_icms = formatar_moeda(get("vBC", icms_tag))
                        aliq_icms = formatar_moeda(get("pICMS", icms_tag))
                if "IPI" in child.tag:
                    ipi_trib = child.find("IPITrib")
                    if ipi_trib is not None:
                        v_ipi = formatar_moeda(get("vIPI", ipi_trib))
                        aliq_ipi = formatar_moeda(get("pIPI", ipi_trib))

        dados["produtos"].append({
            "cprod": get("cProd", prod),
            "xprod": get("xProd", prod),
            "ncm": get("NCM", prod),
            "cst": get("CST", prod) or get("CSOSN", prod),
            "cfop": get("CFOP", prod),
            "ucom": get("uCom", prod),
            "qcom": formatar_quantidade(get("qCom", prod)),
            "vuncom": formatar_moeda(get("vUnCom", prod)),
            "vprod": formatar_moeda(get("vProd", prod)),
            "bc_icms": bc_icms,
            "v_icms": v_icms,
            "aliq_icms": aliq_icms,
            "v_ipi": v_ipi,
            "aliq_ipi": aliq_ipi
        })

    return dados

def gerar_html(dados):
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "danfe_template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template = Template(f.read())
    return template.render(**dados)

def gerar_pdf(html, pdf_output):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8")
    tmp.write(html)
    tmp.close()

    cmd = [
        CHROME_PATH,
        "--headless", "--disable-gpu", "--no-pdf-header-footer",
        "--print-to-pdf-no-header", "--no-margins", "--disable-extensions",
        f"--print-to-pdf={pdf_output}",
        tmp.name
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.unlink(tmp.name)

def processar_xml_zip(zip_path, temp_root):
    work_dir = os.path.join(temp_root, "work")
    os.makedirs(work_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(work_dir)
    
    for root_dir, _, files in os.walk(work_dir):
        for file in files:
            if not file.lower().endswith(".xml"): continue
            xml_path = os.path.join(root_dir, file)
            try:
                dados = xml_to_dict(xml_path)
                data_ref = dados["dh_emi"] if dados["dh_emi"] else "00/00/0000"
                partes = data_ref.split('/')
                ano, mes = (partes[2], partes[1]) if len(partes)==3 else ("0000", "00")
                
                nome_pasta = f"{dados['dest_nome'][:30]} - {dados['dest_cnpj']}".replace('/', '').replace('\\', '').strip()
                pasta_final = os.path.join(BASE_DIR, ano, mes, nome_pasta)
                os.makedirs(pasta_final, exist_ok=True)
                
                shutil.copy(xml_path, os.path.join(pasta_final, file))
                html = gerar_html(dados)
                gerar_pdf(html, os.path.join(pasta_final, file.replace(".xml", ".pdf")))
            except Exception as e:
                print(f"Erro {file}: {e}")

    resultado_path = os.path.join(temp_root, "resultado")
    shutil.make_archive(resultado_path, "zip", BASE_DIR)
    return resultado_path + ".zip"
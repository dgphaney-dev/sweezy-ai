"""Motor heurístico de detecção de sistemas de gestão (POS/ERP) para o ProspectAI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console

console = Console()

try:
    from core.models import ContactChannel, LikelihoodLevel, PixKeyType
except ImportError:
    class LikelihoodLevel(str, Enum):
        HIGH = "HIGH"
        MEDIUM = "MEDIUM"
        LOW = "LOW"

    class PixKeyType(str, Enum):
        CPF = "CPF"
        CNPJ = "CNPJ"
        TELEFONE = "TELEFONE"
        EMAIL = "EMAIL"
        ALEATORIA = "ALEATORIA"
        NONE = "none"

    class ContactChannel(str, Enum):
        WHATSAPP = "WHATSAPP"
        PHONE = "PHONE"
        EMAIL = "EMAIL"
        VISIT = "VISIT"
        TELEFONE = "PHONE"
        VISITA = "VISIT"

class CompetitorCategory(str, Enum):
    ERP_PDV = "ERP_PDV"
    FOOD_DELIVERY = "FOOD_DELIVERY"
    AGENDAMENTO = "AGENDAMENTO"
    ECOMMERCE = "ECOMMERCE"
    SMART_POS = "SMART_POS"

@dataclass(slots=True)
class CompetitorPlatform:
    name: str
    category: CompetitorCategory
    domains: list[str]
    keywords: list[str]
    penalty: int
    description: str

class HeuristicEvaluation(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    business_name: str = Field(..., description="Nome comercial ou fantasia do estabelecimento")
    heuristic_score: int = Field(..., ge=0, le=100, description="Pontuação calculada (0 a 100)")
    likelihood: LikelihoodLevel = Field(..., description="Nível de probabilidade de carência de POS/ERP")
    positive_signals: list[str] = Field(default_factory=list, description="Evidências de processos manuais (dores)")
    red_flags: list[str] = Field(default_factory=list, description="Fatores desqualificadores ou concorrentes encontrados")
    competitors_found: list[str] = Field(default_factory=list, description="Lista de plataformas concorrentes identificadas")
    pain_points: list[str] = Field(default_factory=list, description="Dores operacionais extraídas de reviews")
    pix_key_type: PixKeyType = Field(default=PixKeyType.NONE, description="Tipo de chave PIX detectada")
    has_pdf_menu: bool = Field(default=False, description="Indica presença de cardápio em PDF ou nuvem")
    has_whatsapp_order: bool = Field(default=False, description="Indica pedidos manuais via WhatsApp cru")
    has_online_cart: bool = Field(default=False, description="Indica presença de carrinho transacional moderno")
    details: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais da análise")

_RAW_PLATFORMS: list[tuple[str, CompetitorCategory, list[str], list[str], int, str]] = [
    ("Linx", CompetitorCategory.ERP_PDV, ["linx.com.br", "linxpay.com.br", "microvix.com.br", "linxcommerce.com.br", "dcg.com.br"], ["linx", "microvix", "linxpay", "linxcommerce"], -80, "Líder em software de varejo físico"),
    ("Totvs", CompetitorCategory.ERP_PDV, ["totvs.com.br", "totvs.com", "fly01.com.br", "totvspdv.com.br"], ["totvs", "protheus", "fly01", "totvspdv", "totvsbematech"], -80, "Maior empresa de software de gestão do Brasil"),
    ("Alterdata", CompetitorCategory.ERP_PDV, ["alterdata.com.br", "passaporte.alterdata.com.br", "shop.alterdata.com.br"], ["alterdata", "bimer", "pack alterdata"], -80, "Software de gestão e automação comercial"),
    ("Senior Sistemas", CompetitorCategory.ERP_PDV, ["senior.com.br"], ["senior sistemas", "sapiens", "plataforma senior x"], -80, "ERP corporativo"),
    ("Korp", CompetitorCategory.ERP_PDV, ["korp.com.br"], ["erpkorp", "korp"], -80, "ERP distribuição comercial"),
    ("NCR Aloha", CompetitorCategory.FOOD_DELIVERY, ["ncr.com", "ncraloha.com.br"], ["alohapos", "ncr aloha", "aloha pos"], -80, "PDV alta performance redes/restaurantes"),
    ("ConnectPlug", CompetitorCategory.ERP_PDV, ["connectplug.com.br", "cplug.com.br"], ["connectplug", "cplug"], -80, "PDV em nuvem para food e franquias"),
    ("Hiper (Linx)", CompetitorCategory.ERP_PDV, ["hipersistemas.com.br", "app.hiper.com.br"], ["hipersistemas", "hiper loja", "hiper caixa"], -80, "Gestão para pequeno varejo"),
    ("KCMS", CompetitorCategory.ERP_PDV, ["kcms.com.br", "pedir.delivery", "kcmscloud.com"], ["kcms", "kcmscloud", "pedir.delivery"], -75, "PDV em nuvem para food e varejo"),
    ("Elgin PDV", CompetitorCategory.ERP_PDV, ["elgin.com.br"], ["elginpdv", "elgin automacao"], -75, "Automação comercial Elgin"),
    ("Bematech", CompetitorCategory.ERP_PDV, ["bematech.com.br"], ["bematech", "bemafi32", "totvsbematech"], -75, "Automação comercial tradicional"),
    ("Bling!", CompetitorCategory.ERP_PDV, ["bling.com.br"], ["bling", "bling.com.br/api", "bling.com.br/b/"], -80, "ERP em nuvem e-commerce/varejo"),
    ("Tiny ERP", CompetitorCategory.ERP_PDV, ["tiny.com.br"], ["tinyerp", "tiny.com.br"], -80, "ERP em nuvem Olist para PMEs"),
    ("Omie", CompetitorCategory.ERP_PDV, ["omie.com.br"], ["omie", "omiebox", "omie.com.br/api"], -80, "Gestão integrada em nuvem para PMEs"),
    ("ContaAzul", CompetitorCategory.ERP_PDV, ["contaazul.com"], ["contaazul", "conta azul", "app.contaazul.com"], -80, "Software financeiro/vendas PMEs"),
    ("Sankhya", CompetitorCategory.ERP_PDV, ["sankhya.com.br"], ["sankhya", "sankhyaw", "mge"], -80, "ERP corporativo"),
    ("SAP Business One", CompetitorCategory.ERP_PDV, ["sap.com"], ["sap business one", "sap b1", "sapb1"], -80, "ERP global para PMEs"),
    ("CissPoder", CompetitorCategory.ERP_PDV, ["ciss.com.br"], ["ciss", "cisspoder"], -80, "Automação para supermercados"),
    ("Market Software", CompetitorCategory.ERP_PDV, ["market.com.br"], ["marketgestor", "market software"], -75, "Gestão de supermercados"),
    ("Bluesoft", CompetitorCategory.ERP_PDV, ["bluesoft.com.br"], ["bluesoft", "bluesoftcosmos"], -75, "ERP em nuvem supermercadista"),
    ("MarketUP", CompetitorCategory.ERP_PDV, ["marketup.com"], ["marketup", "pos.marketup.com"], -75, "ERP e PDV gratuito para pequenas empresas"),
    ("Programa NEX", CompetitorCategory.ERP_PDV, ["nextar.com.br", "programanex.com.br"], ["programanex", "nextar", "nex app"], -75, "Frente de caixa para comércio"),
    ("Kyte", CompetitorCategory.ERP_PDV, ["kyteapp.com", "kyte.site"], ["kyteapp", "kyte.site", "kyte pdv"], -70, "PDV no celular"),
    ("Anota AI", CompetitorCategory.FOOD_DELIVERY, ["anota.ai", "pedido.anota.ai", "app.anota.ai"], ["anota.ai", "pedido.anota.ai", "anota ai"], -65, "Atendimento WhatsApp e cardápio digital"),
    ("Goomer", CompetitorCategory.FOOD_DELIVERY, ["goomer.com.br", "goomer.app", "cardapio.goomer.com.br"], ["goomer", "goomer.app", "cardapio.goomer"], -65, "Cardápio QR Code e autoatendimento"),
    ("Saipos", CompetitorCategory.FOOD_DELIVERY, ["saipos.com", "saipos.com.br"], ["saipos", "saipos-delivery", "sistema saipos"], -75, "Gestão de restaurantes e delivery"),
    ("Cardápio Web", CompetitorCategory.FOOD_DELIVERY, ["cardapioweb.com", "cardapioweb.com.br"], ["cardapioweb", "cardapio web"], -60, "Plataforma de delivery online"),
    ("OlaClick", CompetitorCategory.FOOD_DELIVERY, ["olaclick.com", "menu.olaclick.com"], ["olaclick", "menu.olaclick"], -60, "Cardápio digital gratuito integrado com WhatsApp"),
    ("Delivery Direto", CompetitorCategory.FOOD_DELIVERY, ["deliverydireto.com.br"], ["deliverydireto", "delivery direto"], -65, "App e site próprio de delivery"),
    ("InstaDelivery", CompetitorCategory.FOOD_DELIVERY, ["instadelivery.com.br"], ["instadelivery", "instadelivery.com.br"], -60, "Pedidos delivery e PDV para restaurantes"),
    ("Programa Consumer", CompetitorCategory.FOOD_DELIVERY, ["programaconsumer.com.br", "pedir.vc"], ["programaconsumer", "pedir.vc", "consumer connect"], -75, "Gestão de pedidos e comanda móvel"),
    ("Tagme", CompetitorCategory.FOOD_DELIVERY, ["tagme.com.br", "tagmenu.com.br"], ["tagme", "tagmenu", "reservas.tagme"], -65, "Cardápio interativo e reservas"),
    ("GrandChef", CompetitorCategory.FOOD_DELIVERY, ["grandchef.com.br"], ["grandchef", "grand chef"], -70, "Gestão e PDV restaurantes/bares"),
    ("Menew", CompetitorCategory.FOOD_DELIVERY, ["menew.com.br"], ["menew", "sistema menew"], -70, "Automação gastronômica"),
    ("Neemo / Apper", CompetitorCategory.FOOD_DELIVERY, ["neemo.com.br", "deliveryapp.neemo.com.br"], ["neemo", "deliveryapp.neemo"], -65, "Delivery próprio integrado"),
    ("WhatsMenu", CompetitorCategory.FOOD_DELIVERY, ["whatsmenu.com.br"], ["whatsmenu", "pedido.whatsmenu"], -60, "Cardápio pedidos via WhatsApp"),
    ("Hubster / Deliverect", CompetitorCategory.FOOD_DELIVERY, ["hubster.com", "deliverect.com"], ["hubster", "deliverect"], -65, "Agregador de canais delivery"),
    ("ZigPay", CompetitorCategory.FOOD_DELIVERY, ["zigpay.com.br", "zig.fun"], ["zigpay", "zig.fun"], -70, "Solução de consumo cashless"),
    ("iFood Loja / Cardápio", CompetitorCategory.FOOD_DELIVERY, ["cardapio.ifood.com.br", "ifood.com.br/delivery"], ["cardapio.ifood.com.br", "ifood.com.br/delivery"], -50, "Cardápio iFood nativo"),
    ("Nuvemshop", CompetitorCategory.ECOMMERCE, ["nuvemshop.com.br", "tiendanube.com", "cdn.nuvemshop.com.br"], ["nuvemshop", "tiendanube", "cdn.nuvemshop"], -70, "Plataforma de e-commerce"),
    ("Loja Integrada", CompetitorCategory.ECOMMERCE, ["lojaintegrada.com.br"], ["lojaintegrada", "cdn.vtex.com/lojaintegrada"], -70, "E-commerce pequenas lojas"),
    ("Tray", CompetitorCategory.ECOMMERCE, ["tray.com.br", "commerce.tray.com.br"], ["tray.com.br", "commerce.tray"], -70, "Plataforma de e-commerce"),
    ("Shopify", CompetitorCategory.ECOMMERCE, ["shopify.com", "myshopify.com", "cdn.shopify.com"], ["shopify", "myshopify", "cdn.shopify.com"], -70, "E-commerce global com PDV"),
    ("WooCommerce", CompetitorCategory.ECOMMERCE, ["woocommerce.com"], ["woocommerce", "wc-api", "wp-content/plugins/woocommerce"], -65, "E-commerce WordPress"),
    ("VTEX", CompetitorCategory.ECOMMERCE, ["vtex.com", "vtexcommercestable.com.br", "vteximg.com.br"], ["vtex", "vtexcommercestable", "vteximg"], -80, "E-commerce enterprise"),
    ("Magento (Adobe Commerce)", CompetitorCategory.ECOMMERCE, ["magento.com"], ["magento", "mage/cookies.js"], -75, "E-commerce para médias e grandes operações"),
    ("Yampi", CompetitorCategory.ECOMMERCE, ["yampi.com.br", "seguro.yampi.com.br"], ["yampi", "seguro.yampi"], -65, "Checkout transparente"),
    ("CartPanda", CompetitorCategory.ECOMMERCE, ["cartpanda.com"], ["cartpanda"], -65, "Checkout alta conversão"),
    ("Bagy", CompetitorCategory.ECOMMERCE, ["bagy.com.br"], ["bagy.com.br", "bagy"], -65, "E-commerce pequenos negócios"),
    ("Trinks", CompetitorCategory.AGENDAMENTO, ["trinks.com", "app.trinks.com"], ["trinks", "app.trinks.com", "widget.trinks"], -70, "Agendamento online e gestão"),
    ("Avec (BelezaSoft)", CompetitorCategory.AGENDAMENTO, ["avec.com.br", "avecbrasil.com.br", "app.avec.com.br"], ["avec", "avecbrasil", "app.avec"], -70, "ERP mercado de beleza"),
    ("AppBarber / AppBeautician", CompetitorCategory.AGENDAMENTO, ["appbarber.com.br", "appbeautician.com.br"], ["appbarber", "appbeautician"], -70, "Gestão de agendamentos"),
    ("Simples Agenda", CompetitorCategory.AGENDAMENTO, ["simplesagenda.com.br"], ["simplesagenda", "sistema.simplesagenda"], -70, "Gestão de agenda e clientes"),
    ("Doctoralia", CompetitorCategory.AGENDAMENTO, ["doctoralia.com.br"], ["doctoralia", "docplanner"], -70, "Agendamento médico"),
    ("Booksy", CompetitorCategory.AGENDAMENTO, ["booksy.com"], ["booksy"], -70, "Plataforma de agendamento"),
    ("Cielo LIO", CompetitorCategory.SMART_POS, ["cielo.com.br"], ["cielolio", "cielo lio", "cielo.com.br/lio"], -50, "Smart POS com frente de caixa"),
    ("Stone POS / Ton", CompetitorCategory.SMART_POS, ["stone.com.br", "ton.com.br"], ["pos.stone.com.br", "stone pdv", "ton pro"], -50, "Smart POS e pagamentos"),
    ("PagSeguro PagVendas", CompetitorCategory.SMART_POS, ["pagseguro.uol.com.br", "pagvendas.com.br"], ["pagvendas", "pagseguro.uol.com.br/pagvendas"], -50, "App frente de caixa PagBank"),
    ("Mercado Pago Point Smart", CompetitorCategory.SMART_POS, ["mercadopago.com.br"], ["mercadopago.com.br/point", "point smart"], -50, "Smart POS catálogo básico"),
]

COMPETITOR_PLATFORMS: list[CompetitorPlatform] = [
    CompetitorPlatform(name, cat, doms, kws, pen, desc)
    for name, cat, doms, kws, pen, desc in _RAW_PLATFORMS
]

REGEX_WA_URL = re.compile(r"https?://(?:wa\.me|api\.whatsapp\.com/(?:send|message)|web\.whatsapp\.com/send)[^\s\"\'<>]*", re.IGNORECASE)
REGEX_WA_AUTOMATED = re.compile(r"(cardapio|pedido|catalogo|catalog|cart|carrinho|order|token|ref=|checkout)", re.IGNORECASE)
REGEX_PDF_OR_STATIC_MENU = re.compile(r"""href=[\'"]([^\'"]*(?:\.pdf|\.png|\.jpe?g|\.webp|drive\.google\.com|dropbox\.com|onedrive\.live\.com|canva\.com/design|canva\.site|issuu\.com|heyzine\.com)[^\'"]*)[\'"]""", re.IGNORECASE)
REGEX_TEXT_PDF_MENU = re.compile(r"(card[áa]pio\s+em\s+pdf|baixe\s+o\s+card[áa]pio|tabela\s+de\s+pre[çc]os?\s+em\s+pdf|cat[áa]logo\s+em\s+pdf)", re.IGNORECASE)

REGEX_PIX_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
REGEX_PIX_CNPJ = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
REGEX_PIX_EMAIL_PERSONAL = re.compile(r"\b[A-Za-z0-9._%+-]+@(gmail|hotmail|outlook|yahoo|live|icloud)\.com(?:\.br)?\b", re.IGNORECASE)
REGEX_PIX_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
REGEX_PIX_PHONE = re.compile(r"(?:pix[:\s]+)?(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}[-\s]?\d{4})\b", re.IGNORECASE)

FREE_HOSTING_PATTERNS = ["sites.google.com", "wixsite.com", "blogspot.com", "wordpress.com", "canva.site", "linktr.ee", "beacons.ai", "instabio.cc"]
REGEX_MANUAL_SCHEDULING = re.compile(r"(agend(?:e|amentos?)\s+pelo\s+whatsapp|marcar\s+hor[áa]rio\s+pelo\s+direct|agend(?:e|amentos?)\s+via\s+dm|chame\s+no\s+direct\s+para\s+agendar|consulte\s+disponibilidade\s+no\s+chat)", re.IGNORECASE)
REGEX_ONLINE_CART = re.compile(r"(adicionar\s+ao\s+carrinho|finalizar\s+compra|meu\s+carrinho|minha\s+sacola|checkout|shopping-cart)", re.IGNORECASE)

KEYWORDS_POSITIVAS_PROSPECCAO: list[str] = [
    r"\banot(ou|ado|am)\s+no\s+papel\b", r"\bcomanda\s+de\s+papel\b", r"\bbloquinho\b", r"\bcomanda\s+manual\b",
    r"\bsem\s+sistema\b", r"\bsistema\s+caiu\b", r"\bn(ã|a)o\s+tinha\s+sistema\b", r"\banotad(o|a)\s+(à|a)\s+m(ã|a)o\b",
    r"\bperderam\s+(o\s+pedido|a\s+comanda|minha\s+comanda)\b", r"\bmarcaram\s+duas\s+vezes\s+o\s+mesmo\s+hor(á|a)rio\b",
    r"\bconfundiram\s+(os\s+pedidos|as\s+mesas)\b", r"\bfila\s+(enorme|grande|imensa)\s+no\s+caixa\b",
    r"\bdemora\s+(absurda|demais|muito)\s+para\s+pagar\b", r"\bdemor(ou|am)\s+para\s+(trazer|fechar)\s+a\s+conta\b",
    r"\bn(ã|a)o\s+tinham\s+troco\b", r"\bconta\s+errada\b", r"\bcobraram\s+a\s+mais\b", r"\bcaixa\s+lento\b",
    r"\bmaquininha\s+(n(ã|a)o\s+pegava|sem\s+sinal|lenta)\b", r"\bdesorganiza(ç|c)(ã|a)o\s+no\s+atendimento\b",
]

KEYWORDS_NEGATIVAS_PROSPECCAO: list[str] = [
    r"\bcard(á|a)pio\s+digital\b", r"\bpedi(do|mos)\s+pelo\s+(tablet|celular|qrcode|qr\s+code)\b",
    r"\btotem\s+de\s+autoatendimento\b", r"\baplicativo\s+pr(ó|o)prio\b", r"\bsistema\s+muito\s+r(á|a)pido\b",
    r"\bpainel\s+eletr(ô|o)nico\b", r"\bfechamento\s+autom(á|a)tico\b", r"\bpedi\s+pelo\s+ifood\b", r"\bapp\s+super\s+f(á|a)cil\b",
]

def validate_cpf(cpf: str) -> bool:
    digits = [int(d) for d in cpf if d.isdigit()]
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    rem_1 = sum(d * (10 - i) for i, d in enumerate(digits[:9])) % 11
    if digits[9] != (0 if rem_1 < 2 else 11 - rem_1):
        return False
    rem_2 = sum(d * (11 - i) for i, d in enumerate(digits[:10])) % 11
    return digits[10] == (0 if rem_2 < 2 else 11 - rem_2)

def validate_cnpj(cnpj: str) -> bool:
    digits = [int(d) for d in cnpj if d.isdigit()]
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    rem_1 = sum(n * w for n, w in zip(digits[:12], w1, strict=True)) % 11
    if digits[12] != (0 if rem_1 < 2 else 11 - rem_1):
        return False
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    rem_2 = sum(n * w for n, w in zip(digits[:13], w2, strict=True)) % 11
    return digits[13] == (0 if rem_2 < 2 else 11 - rem_2)

class ReviewAnalyzer:
    def __init__(self) -> None:
        self.positive_patterns = [re.compile(p, re.IGNORECASE) for p in KEYWORDS_POSITIVAS_PROSPECCAO]
        self.negative_patterns = [re.compile(p, re.IGNORECASE) for p in KEYWORDS_NEGATIVAS_PROSPECCAO]

    def analyze(self, reviews: list[dict[str, Any]]) -> dict[str, Any]:
        score_delta = 0
        positive_evidences: list[dict[str, str]] = []
        negative_evidences: list[dict[str, str]] = []
        for review in reviews:
            text: str = ""
            if isinstance(review, dict):
                text_obj = review.get("text")
                if isinstance(text_obj, dict):
                    text = text_obj.get("text", "")
                elif isinstance(text_obj, str):
                    text = text_obj
                elif "originalText" in review:
                    orig = review["originalText"]
                    text = orig.get("text", "") if isinstance(orig, dict) else str(orig)
            elif isinstance(review, str):
                text = review
            if not text:
                continue
            author = "Cliente"
            if isinstance(review, dict):
                author = review.get("authorAttribution", {}).get("displayName") or review.get("author_name") or "Cliente"
            for pattern in self.positive_patterns:
                match = pattern.search(text)
                if match:
                    score_delta += 25
                    start = max(0, match.start() - 35)
                    end = min(len(text), match.end() + 35)
                    snippet = text[start:end].replace("\n", " ").strip()
                    positive_evidences.append({"termo": match.group(0), "trecho": f"...{snippet}...", "autor": author})
                    break
            for pattern in self.negative_patterns:
                match = pattern.search(text)
                if match:
                    score_delta -= 30
                    start = max(0, match.start() - 35)
                    end = min(len(text), match.end() + 35)
                    snippet = text[start:end].replace("\n", " ").strip()
                    negative_evidences.append({"termo": match.group(0), "trecho": f"...{snippet}...", "autor": author})
                    break
        return {"score_delta": score_delta, "positive_evidences": positive_evidences, "negative_evidences": negative_evidences}

class POSDetector:
    def __init__(self, catalog: list[CompetitorPlatform] | None = None) -> None:
        self.catalog = catalog or COMPETITOR_PLATFORMS
        self.review_analyzer = ReviewAnalyzer()

    def detect_competitors(self, html_content: str | None, website_url: str | None) -> list[CompetitorPlatform]:
        detected: list[CompetitorPlatform] = []
        text_to_scan = f"{website_url or ''} {html_content or ''}".lower()
        for platform in self.catalog:
            matched = False
            for domain in platform.domains:
                if domain.lower() in text_to_scan:
                    detected.append(platform)
                    matched = True
                    break
            if matched:
                continue
            for keyword in platform.keywords:
                if keyword.lower() in text_to_scan:
                    detected.append(platform)
                    break
        return detected

    def detect_pix_key(self, text: str | None) -> tuple[PixKeyType, str | None]:
        if not text:
            return PixKeyType.NONE, None
        for cand in REGEX_PIX_CNPJ.findall(text):
            if validate_cnpj(cand):
                return PixKeyType.CNPJ, cand
        for cand in REGEX_PIX_CPF.findall(text):
            if validate_cpf(cand):
                return PixKeyType.CPF, cand
        email_match = REGEX_PIX_EMAIL_PERSONAL.search(text)
        if email_match:
            return PixKeyType.EMAIL, email_match.group(0)
        if "pix" in text.lower():
            phone_match = REGEX_PIX_PHONE.search(text)
            if phone_match:
                return PixKeyType.TELEFONE, phone_match.group(0)
            uuid_match = REGEX_PIX_UUID.search(text)
            if uuid_match:
                return PixKeyType.ALEATORIA, uuid_match.group(0)
        return PixKeyType.NONE, None

    def evaluate(
        self,
        name: str,
        website_url: str | None = None,
        html_content: str | None = None,
        whatsapp_urls: list[str] | None = None,
        reviews: list[dict[str, Any]] | None = None,
        cnpj_data: dict[str, Any] | None = None,
    ) -> HeuristicEvaluation:
        score = 0
        positive_signals: list[str] = []
        red_flags: list[str] = []
        competitors_found: list[str] = []
        pain_points: list[str] = []
        html = html_content or ""
        urls_wa = whatsapp_urls or []
        revs = reviews or []

        detected_platforms = self.detect_competitors(html, website_url)
        for platform in detected_platforms:
            competitors_found.append(platform.name)
            red_flags.append(f"PENALIDADE: Concorrente '{platform.name}' ({platform.category.value}) detectado [{platform.penalty} pts]")
            score += platform.penalty

        has_website = bool(website_url and website_url.strip())
        is_social_only = False
        if not has_website:
            score += 15
            positive_signals.append("SIG_SEM_WEBSITE: Sem website próprio dedicado (+15)")
        else:
            url_lower = website_url.lower() if website_url else ""
            if any(dom in url_lower for dom in ["instagram.com", "facebook.com", "wa.me"]):
                is_social_only = True
                score += 15
                positive_signals.append("SIG_SEM_WEBSITE: Website redireciona apenas para rede social/chat (+15)")
            if any(free in url_lower for free in FREE_HOSTING_PATTERNS):
                score += 15
                positive_signals.append("SIG_SITE_GRATUITO: Hospedagem básica gratuita sem e-commerce (+15)")

        has_pdf_menu = False
        if html and (REGEX_PDF_OR_STATIC_MENU.search(html) or REGEX_TEXT_PDF_MENU.search(html)):
            has_pdf_menu = True
            score += 25
            positive_signals.append("SIG_CARDAPIO_PDF: Catálogo/cardápio estático em PDF, Imagem ou Nuvem (+25)")

        has_whatsapp_order = False
        raw_wa_detected = False
        for wa in urls_wa:
            if "wa.me" in wa.lower() or "api.whatsapp.com" in wa.lower():
                has_whatsapp_order = True
                if not REGEX_WA_AUTOMATED.search(wa):
                    raw_wa_detected = True

        if raw_wa_detected:
            score += 20
            positive_signals.append("SIG_WHATSAPP_CRU: Atendimento manual via link de WhatsApp sem automação de carrinho (+20)")

        if html and REGEX_MANUAL_SCHEDULING.search(html):
            score += 20
            positive_signals.append("SIG_SEM_AGENDAMENTO: Agendamentos orientados manualmente via WhatsApp/Direct (+20)")

        pix_type, _ = self.detect_pix_key(html)
        if pix_type in (PixKeyType.CPF, PixKeyType.EMAIL):
            score += 15
            positive_signals.append(f"SIG_PIX_PESSOAL: Chave Pix informal ({pix_type.value}) sem conciliação bancária PJ (+15)")

        has_online_cart = False
        if html and REGEX_ONLINE_CART.search(html):
            has_online_cart = True
            if not detected_platforms:
                score -= 30
                red_flags.append("PEN_ECOMMERCE_GENERICO: Presença de carrinho online estruturado (-30)")

        if revs:
            rev_analysis = self.review_analyzer.analyze(revs)
            score += rev_analysis["score_delta"]
            for pos in rev_analysis["positive_evidences"]:
                pain_points.append(f"{pos['autor']}: \"{pos['trecho']}\"")
                positive_signals.append(f"SIG_REVIEW_DOR: {pos['termo']} (+25)")
            for neg in rev_analysis["negative_evidences"]:
                red_flags.append(f"PEN_REVIEW_SISTEMA: {neg['termo']} (-30)")

        if cnpj_data:
            porte = str(cnpj_data.get("porte", "")).upper()
            if "MEI" in porte or porte in ("01", "ME"):
                score += 10
                positive_signals.append(f"SIG_PORTE_MEI_ME: Porte empresarial pequeno ({porte}) (+10)")
            abertura = cnpj_data.get("data_abertura") or cnpj_data.get("data_inicio_atividade")
            if abertura and "MEI" in porte:
                score += 5
                positive_signals.append("SIG_IDADE_NOVA: Microempresa em fase de estruturação (+5)")

        final_score = max(0, min(100, score))
        if final_score >= 70:
            likelihood = LikelihoodLevel.HIGH
        elif final_score >= 40:
            likelihood = LikelihoodLevel.MEDIUM
        else:
            likelihood = LikelihoodLevel.LOW

        return HeuristicEvaluation(
            business_name=name,
            heuristic_score=final_score,
            likelihood=likelihood,
            positive_signals=positive_signals,
            red_flags=red_flags,
            competitors_found=list(set(competitors_found)),
            pain_points=pain_points,
            pix_key_type=pix_type,
            has_pdf_menu=has_pdf_menu,
            has_whatsapp_order=has_whatsapp_order,
            has_online_cart=has_online_cart,
            details={
                "has_website": has_website and not is_social_only,
                "raw_score_before_clamp": score,
                "detected_platforms_count": len(detected_platforms),
                "reviews_analyzed_count": len(revs),
            },
        )

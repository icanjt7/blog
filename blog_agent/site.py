from __future__ import annotations

import html
import hashlib
import json
import re
import shutil
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import markdown
import yaml

from .images import ImageAgent


@dataclass
class Post:
    title: str
    date: datetime
    category: str
    tags: list[str]
    slug: str
    excerpt: str
    body_html: str
    cover_image: str = ""
    cover_image_alt: str = ""
    author: str = ""


AUTHOR_NAMES = [
    "알렉스",
    "민준",
    "서윤",
    "지호",
    "하린",
    "도윤",
    "유진",
    "리아",
    "현우",
    "나윤",
]

GTM_CONTAINER_ID = "GTM-PRH78BZK"

LANGUAGE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("ko", "한국어"),
    ("en", "English"),
    ("ja", "日本語"),
    ("zh-CN", "中文"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("pt", "Português"),
    ("vi", "Tiếng Việt"),
    ("id", "Indonesia"),
    ("th", "ไทย"),
    ("ar", "العربية"),
)

LANGUAGE_BASE_ALIASES: dict[str, str] = {
    "zh": "zh-CN",
}

GOVERNMENT_GLOBAL_PAGES: dict[str, dict[str, str]] = {
    "ko": {
        "filename": "government-press.html",
        "title": "한국 정부·공공기관 보도기사",
        "kicker": "공식 발표 글로벌 검색 허브",
        "description": "한국 정부부처와 공공기관의 보도기사를 한곳에서 확인할 수 있는 페이지입니다.",
        "intro": "재정, 기술, 문화, 보건, 안전, 고용, 교통 등 주요 정부·공공기관 발표를 분야별 기사로 정리합니다.",
        "terms": "한국 정부 보도자료, 공공기관 소식, 중앙부처 발표, 정책 브리핑",
        "lang_name": "한국어",
    },
    "en": {
        "filename": "government-press-en.html",
        "title": "Korean Government and Public Agency Press Articles",
        "kicker": "Global search hub for official Korean announcements",
        "description": "Browse Korean ministry and public agency press articles on policy, technology, culture, health, safety, labor, transport, and public services.",
        "intro": "BriefWave curates official announcements from Korean ministries and public institutions into readable news briefings with source-oriented context.",
        "terms": "Korean government press release, South Korea ministry news, public agency announcement, policy briefing Korea",
        "lang_name": "English",
    },
    "ja": {
        "filename": "government-press-ja.html",
        "title": "韓国政府・公共機関のプレス記事",
        "kicker": "韓国公式発表の検索ハブ",
        "description": "韓国の省庁・公共機関による政策、技術、文化、保健、安全、雇用、交通分野の発表記事をまとめています。",
        "intro": "BriefWaveは韓国政府と公共機関の公式発表を、読みやすいニュース形式で整理します。",
        "terms": "韓国政府プレスリリース, 韓国省庁ニュース, 公共機関発表, 韓国政策ブリーフィング",
        "lang_name": "日本語",
    },
    "zh-CN": {
        "filename": "government-press-zh-cn.html",
        "title": "韩国政府和公共机构新闻稿文章",
        "kicker": "韩国官方公告全球搜索入口",
        "description": "查看韩国政府部门和公共机构有关政策、科技、文化、卫生、安全、就业、交通和公共服务的新闻文章。",
        "intro": "BriefWave 将韩国政府和公共机构的官方公告整理成便于阅读的新闻简报。",
        "terms": "韩国政府新闻稿, 韩国部委新闻, 公共机构公告, 韩国政策简报",
        "lang_name": "中文",
    },
    "es": {
        "filename": "government-press-es.html",
        "title": "Artículos de prensa del gobierno y agencias públicas de Corea",
        "kicker": "Centro global de búsqueda para anuncios oficiales de Corea",
        "description": "Consulta artículos sobre comunicados de ministerios y agencias públicas de Corea en política, tecnología, cultura, salud, seguridad, empleo y transporte.",
        "intro": "BriefWave organiza anuncios oficiales de ministerios e instituciones públicas de Corea en resúmenes informativos legibles.",
        "terms": "comunicado del gobierno coreano, noticias de ministerios de Corea, agencia pública Corea, política pública Corea",
        "lang_name": "Español",
    },
    "fr": {
        "filename": "government-press-fr.html",
        "title": "Articles de presse du gouvernement et des organismes publics coréens",
        "kicker": "Hub de recherche mondial pour les annonces officielles coréennes",
        "description": "Retrouvez les annonces des ministères et organismes publics coréens sur les politiques, la technologie, la culture, la santé, la sécurité, l'emploi et les transports.",
        "intro": "BriefWave transforme les annonces officielles coréennes en synthèses d'actualité lisibles et contextualisées.",
        "terms": "communiqué du gouvernement coréen, actualités ministères Corée, organisme public Corée, politique publique Corée",
        "lang_name": "Français",
    },
    "de": {
        "filename": "government-press-de.html",
        "title": "Presseartikel koreanischer Ministerien und öffentlicher Einrichtungen",
        "kicker": "Globaler Suchhub für offizielle Ankündigungen aus Korea",
        "description": "Lesen Sie Artikel zu Mitteilungen koreanischer Ministerien und öffentlicher Einrichtungen über Politik, Technologie, Kultur, Gesundheit, Sicherheit, Arbeit und Verkehr.",
        "intro": "BriefWave bereitet offizielle Meldungen aus Korea als verständliche Nachrichtenbriefings auf.",
        "terms": "Pressemitteilung koreanische Regierung, Ministerium Korea Nachrichten, öffentliche Einrichtung Korea, Politikbriefing Korea",
        "lang_name": "Deutsch",
    },
    "pt": {
        "filename": "government-press-pt.html",
        "title": "Artigos de imprensa do governo e órgãos públicos da Coreia",
        "kicker": "Hub global de busca para anúncios oficiais da Coreia",
        "description": "Veja artigos sobre comunicados de ministérios e órgãos públicos coreanos em política, tecnologia, cultura, saúde, segurança, trabalho e transporte.",
        "intro": "O BriefWave organiza anúncios oficiais da Coreia em briefings de notícias claros e contextualizados.",
        "terms": "comunicado do governo coreano, notícias ministérios Coreia, agência pública Coreia, política pública Coreia",
        "lang_name": "Português",
    },
    "vi": {
        "filename": "government-press-vi.html",
        "title": "Bài viết thông cáo của chính phủ và cơ quan công Hàn Quốc",
        "kicker": "Trung tâm tìm kiếm toàn cầu cho thông báo chính thức của Hàn Quốc",
        "description": "Theo dõi bài viết về thông cáo của bộ ngành và cơ quan công Hàn Quốc trong chính sách, công nghệ, văn hóa, y tế, an toàn, lao động và giao thông.",
        "intro": "BriefWave biên tập thông báo chính thức của Hàn Quốc thành các bản tin dễ đọc, có bối cảnh.",
        "terms": "thông cáo chính phủ Hàn Quốc, tin bộ ngành Hàn Quốc, cơ quan công Hàn Quốc, chính sách Hàn Quốc",
        "lang_name": "Tiếng Việt",
    },
    "id": {
        "filename": "government-press-id.html",
        "title": "Artikel siaran pers pemerintah dan lembaga publik Korea",
        "kicker": "Pusat pencarian global untuk pengumuman resmi Korea",
        "description": "Temukan artikel pengumuman kementerian dan lembaga publik Korea tentang kebijakan, teknologi, budaya, kesehatan, keselamatan, tenaga kerja, dan transportasi.",
        "intro": "BriefWave menyusun pengumuman resmi Korea menjadi ringkasan berita yang mudah dibaca.",
        "terms": "siaran pers pemerintah Korea, berita kementerian Korea, lembaga publik Korea, kebijakan Korea",
        "lang_name": "Indonesia",
    },
    "th": {
        "filename": "government-press-th.html",
        "title": "บทความข่าวประชาสัมพันธ์รัฐบาลและหน่วยงานสาธารณะเกาหลี",
        "kicker": "ศูนย์ค้นหาระดับโลกสำหรับประกาศทางการของเกาหลี",
        "description": "อ่านบทความจากกระทรวงและหน่วยงานสาธารณะของเกาหลีเกี่ยวกับนโยบาย เทคโนโลยี วัฒนธรรม สุขภาพ ความปลอดภัย แรงงาน และการคมนาคม",
        "intro": "BriefWave จัดเรียงประกาศทางการของเกาหลีเป็นบทสรุปข่าวที่อ่านง่ายและมีบริบท",
        "terms": "ข่าวประชาสัมพันธ์รัฐบาลเกาหลี, ข่าวกระทรวงเกาหลี, หน่วยงานสาธารณะเกาหลี, นโยบายเกาหลี",
        "lang_name": "ไทย",
    },
    "ar": {
        "filename": "government-press-ar.html",
        "title": "مقالات بيانات الحكومة والهيئات العامة الكورية",
        "kicker": "مركز بحث عالمي للإعلانات الرسمية الكورية",
        "description": "تابع مقالات عن بيانات الوزارات والهيئات العامة في كوريا حول السياسات والتقنية والثقافة والصحة والسلامة والعمل والنقل.",
        "intro": "يقوم BriefWave بتنظيم الإعلانات الرسمية الكورية في موجزات إخبارية واضحة وسهلة القراءة.",
        "terms": "بيان صحفي للحكومة الكورية, أخبار وزارات كوريا, هيئة عامة كورية, سياسات كوريا",
        "lang_name": "العربية",
    },
}

LOCALIZED_POST_COPY: dict[str, dict[str, str]] = {
    "en": {
        "label": "English search version",
            "notice": "This page helps international readers and search engines discover the original Korean article. Use the language selector to read the full article in your preferred language.",
            "original": "Original Korean article",
            "summary": "Korean article summary",
            "keywords": "Related multilingual search keywords",
            "read": "Read the original article",
        },
    "ja": {
        "label": "日本語検索版",
            "notice": "このページは、海外の読者と検索エンジンが韓国語の元記事を見つけやすくするためのページです。全文は言語セレクターで翻訳して読めます。",
            "original": "韓国語の元記事",
            "summary": "韓国語記事の要約",
            "keywords": "関連する多言語検索キーワード",
            "read": "元記事を読む",
        },
    "zh-CN": {
        "label": "中文搜索版本",
            "notice": "本页面用于帮助国际读者和搜索引擎发现原始韩文文章。可使用语言选择器阅读完整译文。",
            "original": "韩文原文",
            "summary": "韩文文章摘要",
            "keywords": "相关多语言搜索关键词",
            "read": "阅读韩文原文",
        },
    "es": {
        "label": "Versión de búsqueda en español",
            "notice": "Esta página ayuda a lectores internacionales y motores de búsqueda a encontrar el artículo original en coreano. Usa el selector de idioma para leerlo traducido.",
            "original": "Artículo original en coreano",
            "summary": "Resumen del artículo en coreano",
            "keywords": "Palabras clave multilingües relacionadas",
            "read": "Leer el artículo original",
        },
    "fr": {
        "label": "Version de recherche en français",
            "notice": "Cette page aide les lecteurs internationaux et les moteurs de recherche à trouver l'article coréen original. Utilisez le sélecteur de langue pour lire la traduction complète.",
            "original": "Article original en coréen",
            "summary": "Résumé de l'article coréen",
            "keywords": "Mots-clés multilingues associés",
            "read": "Lire l'article original",
        },
    "de": {
        "label": "Deutsche Suchversion",
            "notice": "Diese Seite hilft internationalen Leserinnen und Lesern sowie Suchmaschinen, den koreanischen Originalartikel zu finden. Nutzen Sie die Sprachauswahl für die vollständige Übersetzung.",
            "original": "Koreanischer Originalartikel",
            "summary": "Zusammenfassung des koreanischen Artikels",
            "keywords": "Verwandte mehrsprachige Suchbegriffe",
            "read": "Originalartikel lesen",
        },
    "pt": {
        "label": "Versão de busca em português",
            "notice": "Esta página ajuda leitores internacionais e mecanismos de busca a encontrar o artigo original em coreano. Use o seletor de idioma para ler a tradução completa.",
            "original": "Artigo original em coreano",
            "summary": "Resumo do artigo em coreano",
            "keywords": "Palavras-chave multilíngues relacionadas",
            "read": "Ler o artigo original",
        },
    "vi": {
        "label": "Phiên bản tìm kiếm tiếng Việt",
            "notice": "Trang này giúp độc giả quốc tế và công cụ tìm kiếm tìm thấy bài viết gốc bằng tiếng Hàn. Hãy dùng bộ chọn ngôn ngữ để đọc bản dịch đầy đủ.",
            "original": "Bài viết gốc tiếng Hàn",
            "summary": "Tóm tắt bài viết tiếng Hàn",
            "keywords": "Từ khóa tìm kiếm đa ngôn ngữ liên quan",
            "read": "Đọc bài viết gốc",
        },
    "id": {
        "label": "Versi pencarian bahasa Indonesia",
            "notice": "Halaman ini membantu pembaca internasional dan mesin pencari menemukan artikel asli berbahasa Korea. Gunakan pemilih bahasa untuk membaca terjemahan lengkap.",
            "original": "Artikel asli bahasa Korea",
            "summary": "Ringkasan artikel bahasa Korea",
            "keywords": "Kata kunci pencarian multibahasa terkait",
            "read": "Baca artikel asli",
        },
    "th": {
        "label": "เวอร์ชันค้นหาภาษาไทย",
            "notice": "หน้านี้ช่วยให้ผู้อ่านต่างประเทศและเครื่องมือค้นหาพบบทความต้นฉบับภาษาเกาหลี ใช้ตัวเลือกภาษาเพื่ออ่านคำแปลฉบับเต็ม",
            "original": "บทความต้นฉบับภาษาเกาหลี",
            "summary": "สรุปบทความภาษาเกาหลี",
            "keywords": "คำค้นหาหลายภาษาที่เกี่ยวข้อง",
            "read": "อ่านบทความต้นฉบับ",
        },
    "ar": {
        "label": "نسخة بحث عربية",
            "notice": "تساعد هذه الصفحة القراء الدوليين ومحركات البحث على العثور على المقال الكوري الأصلي. استخدم محدد اللغة لقراءة الترجمة الكاملة.",
            "original": "المقال الكوري الأصلي",
            "summary": "ملخص المقال الكوري",
            "keywords": "كلمات بحث متعددة اللغات ذات صلة",
            "read": "قراءة المقال الأصلي",
        },
}

SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "핫이슈": ("hot issue", "breaking news", "trend", "local news", "travel", "restaurant", "cafe", "旅游", "旅行", "ニュース", "tendencia"),
    "기술": ("technology", "tech", "it", "gadget", "ai", "software", "device", "科技", "技术", "技術", "tecnologia"),
    "정책": ("policy", "government", "finance", "subsidy", "support", "economy", "政策", "政府", "政策", "politica"),
    "생활": ("life", "lifestyle", "living", "tips", "benefits", "family", "生活", "暮らし", "vida"),
    "정치": ("politics", "election", "candidate", "pledge", "civic", "政治", "選挙", "politica"),
    "여행": ("travel", "trip", "tour", "tourism", "旅行", "旅游", "viaje"),
    "맛집": ("restaurant", "food", "dining", "place to eat", "グルメ", "餐厅", "comida"),
    "카페": ("cafe", "coffee", "咖啡", "カフェ"),
    "지원금": ("subsidy", "grant", "benefit", "support payment", "补贴", "補助金"),
    "혜택": ("benefit", "discount", "support", "优惠", "特典"),
    "선거": ("election", "vote", "candidate", "選挙", "选举"),
    "공약": ("pledge", "promise", "campaign promise", "公約", "承诺"),
    "보도기사": ("press release", "official release", "government news", "新闻稿", "プレスリリース"),
    "AI": ("artificial intelligence", "machine learning", "生成 ai", "人工智能", "inteligencia artificial"),
    "인공지능": ("ai", "artificial intelligence", "machine learning", "人工智能", "人工知能"),
    "Apple": ("apple", "iphone", "ipad", "mac", "siri"),
    "Rivian": ("rivian", "ev", "electric vehicle", "electric suv"),
    "전기차": ("ev", "electric vehicle", "electric car", "电动车", "電気自動車"),
    "대한민국": ("korea", "south korea", "republic of korea", "韓国", "韩国", "corea"),
    "정부": ("government", "ministry", "public sector", "official", "政府", "政府機関", "gobierno"),
    "공공기관": ("public institution", "public agency", "government agency", "公共機関", "公共机构"),
    "행정안전부": ("ministry of the interior and safety", "mois", "korean interior ministry", "韓国 行政安全部", "韩国行政安全部"),
    "과학기술정보통신부": ("ministry of science and ict", "msit", "science ministry", "ict ministry", "韓国 科学技術情報通信部", "韩国科学技术信息通信部"),
    "재정경제부": ("ministry of economy and finance", "ministry of finance", "mofe", "korean finance ministry", "韓国 財政経済部", "韩国财政经济部"),
    "기획재정부": ("ministry of economy and finance", "ministry of finance", "mofe", "korean finance ministry", "韓国 企画財政部", "韩国企划财政部"),
    "문화체육관광부": ("ministry of culture sports and tourism", "mcst", "culture ministry", "tourism ministry", "韓国 文化体育観光部", "韩国文化体育观光部"),
    "국가유산청": ("korea heritage service", "cultural heritage administration", "khs", "heritage agency", "韓国 国家遺産庁", "韩国国家遗产厅"),
    "국가유산진흥원": ("korea heritage agency", "korea heritage service foundation", "kh", "heritage foundation", "韓国 国家遺産振興院", "韩国国家遗产振兴院"),
    "교육부": ("ministry of education", "education ministry", "韓国 教育部", "韩国教育部"),
    "국토교통부": ("ministry of land infrastructure and transport", "molit", "transport ministry", "land ministry"),
    "보건복지부": ("ministry of health and welfare", "mohw", "health ministry", "welfare ministry"),
    "고용노동부": ("ministry of employment and labor", "moel", "labor ministry", "employment ministry"),
    "외교부": ("ministry of foreign affairs", "mofa", "foreign ministry"),
    "국방부": ("ministry of national defense", "mnd", "defense ministry"),
    "법무부": ("ministry of justice", "justice ministry"),
    "산업통상부": ("ministry of trade industry and energy", "motie", "industry ministry"),
    "중소벤처기업부": ("ministry of smes and startups", "mss", "startup ministry"),
    "환경부": ("ministry of environment", "environment ministry"),
    "기후에너지환경부": ("ministry of climate energy and environment", "climate ministry", "environment ministry"),
    "농림축산식품부": ("ministry of agriculture food and rural affairs", "mafra", "agriculture ministry"),
    "해양수산부": ("ministry of oceans and fisheries", "mof", "oceans ministry", "fisheries ministry"),
    "식품의약품안전처": ("ministry of food and drug safety", "mfds", "food drug safety"),
    "질병관리청": ("korea disease control and prevention agency", "kdca", "disease control agency"),
    "소방청": ("national fire agency", "nfa", "fire agency"),
    "경찰청": ("korean national police agency", "knpa", "police agency"),
    "국민권익위원회": ("anti-corruption and civil rights commission", "acrc", "civil rights commission"),
    "국가보훈부": ("ministry of patriots and veterans affairs", "mpva", "veterans ministry"),
    "원자력안전위원회": ("nuclear safety and security commission", "nssc", "nuclear safety commission"),
}


class StaticSiteBuilder:
    def __init__(
        self,
        posts_dir: Path,
        public_dir: Path,
        site_title: str,
        site_description: str,
        custom_domain: str | None = None,
        categories: list[str] | None = None,
        ga_measurement_id: str | None = None,
        adsense_publisher_id: str | None = None,
    ) -> None:
        self.posts_dir = posts_dir
        self.public_dir = public_dir
        self.site_title = site_title
        self.site_description = site_description
        self.custom_domain = custom_domain
        self.categories = categories or []
        self.ga_measurement_id = ga_measurement_id
        self.adsense_publisher_id = adsense_publisher_id
        self.site_url = f"https://{self.custom_domain.strip()}" if self.custom_domain else "https://briefwave.kr"

    def build(self) -> None:
      if self.public_dir.exists():
        shutil.rmtree(self.public_dir)
      self.public_dir.mkdir(parents=True, exist_ok=True)
      posts = self._load_posts()
      # Auto-extend nav categories with any category found in posts but not yet listed.
      seen_cats = {p.category for p in posts}
      for cat in seen_cats:
          if cat and cat not in self.categories:
              self.categories.append(cat)
      for post in posts:
        self._write_post(post)

      self._write_index(posts)
      # generate search index and page
      self._write_search_index(posts)
      self._write_search_page(posts)
      self._write_global_government_pages(posts)
      self._write_category_pages(posts)

      # self._write_dashboard(posts)  # 관리자 전용 — 일반 사용자에게 노출하지 않음
      self._write_feed(posts)
      self._write_sitemap(posts)
      self._write_css()
      self._write_favicon()
      self._write_robots()
      self._copy_assets()
      self._write_cname()

    def _load_posts(self) -> list[Post]:
        if not self.posts_dir.exists():
            return []
        posts = [self._parse_post(path) for path in sorted(self.posts_dir.glob("*.md"))]
        return sorted(posts, key=lambda post: post.date, reverse=True)

    def _parse_post(self, path: Path) -> Post:
        raw = path.read_text(encoding="utf-8")
        meta: dict = {}
        body = raw
        if raw.startswith("---"):
            match = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", raw, flags=re.S)
            if not match:
                raise ValueError(f"Unclosed frontmatter in {path}")
            frontmatter = match.group(1)
            body = raw[match.end():]
            try:
                meta = yaml.safe_load(frontmatter) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid frontmatter YAML in {path}") from exc
        title = str(meta.get("title") or path.stem)
        date = self._parse_date(str(meta.get("date") or datetime.now().isoformat()))
        _cat_map = {"tech": "기술", "living": "생활", "finance": "정책", "local": "핫이슈"}
        category = str(meta.get("category") or "생활")
        category = _cat_map.get(category, category)
        tags = [str(tag) for tag in meta.get("tags", [])]
        raw_cover_image = str(meta.get("cover_image") or "")
        body = self._strip_leading_image(body)
        body_html = markdown.markdown(
            body,
            extensions=["tables", "fenced_code", "toc"],
            output_format="html5",
        )
        # wrap tables for horizontal scroll on mobile
        body_html = body_html.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
        excerpt = self._excerpt(body)
        cover_image = raw_cover_image
        if not cover_image or "picsum.photos" in cover_image:
            cover_image = self._fallback_cover_image(title, category, tags, path.stem)
        return Post(
            title=title,
            date=date,
            category=category,
            tags=tags,
            slug=path.stem,
            excerpt=excerpt,
            body_html=body_html,
            cover_image=cover_image,
            cover_image_alt=str(meta.get("cover_image_alt") or f"{title} 관련 대표 이미지"),
            author=str(meta.get("author") or self._author_for_slug(path.stem)),
        )

    def _slugify(self, value: str) -> str:
        normalized = value.strip().lower()
        return re.sub(r"[^\w가-힣-]+", "-", normalized).strip("-") or "category"

    def _page_url(self, filename: str) -> str:
        if filename == "index.html":
            return self.site_url + "/"
        return f"{self.site_url}/{filename}"

    def _nav_html(self, active: str | None = None, prefix: str = "./") -> str:
        items = [
            f'<a href="{prefix}index.html" class="' + ("active" if active == "홈" else "") + '">홈</a>'
        ]
        for category in self.categories:
            href = f"{prefix}category-{self._slugify(category)}.html"
            active_class = "active" if active == category else ""
            items.append(f'<a href="{href}" class="{active_class}">{html.escape(category)}</a>')
        return '<nav class="site-nav">' + "".join(items) + '</nav>'

    def _language_switcher_html(self) -> str:
        options = "\n".join(
            f'            <option value="{html.escape(code)}">{html.escape(label)}</option>'
            for code, label in LANGUAGE_OPTIONS
        )
        return f"""<div class="language-switcher">
          <select id="language-select" aria-label="Language">
{options}
          </select>
          <div id="google_translate_element" class="translate-host" aria-hidden="true"></div>
        </div>"""

    def _category_page_filename(self, category: str) -> str:
        return f"category-{self._slugify(category)}.html"

    @staticmethod
    def _language_dir(code: str) -> str:
        return code.lower()

    def _localized_post_filename(self, post: Post, lang: str) -> str:
        if lang == "ko":
            return f"{post.slug}.html"
        return f"{self._language_dir(lang)}/{post.slug}.html"

    def _post_alternate_urls(self, post: Post) -> dict[str, str]:
        canonical = self._page_url(self._localized_post_filename(post, "ko"))
        return {"ko": canonical, "x-default": canonical}

    @staticmethod
    def _author_for_slug(slug: str) -> str:
        digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()
        return AUTHOR_NAMES[int(digest[:8], 16) % len(AUTHOR_NAMES)]

    _INSTITUTION_VISUALS: dict[str, str] = {
        "행정안전부": "government administration building",
        "과학기술정보통신부": "science technology research laboratory",
        "재정경제부": "economy finance chart government",
        "문화체육관광부": "culture arts tourism",
        "국가유산청": "korean heritage palace architecture",
        "국가유산진흥원": "traditional korean culture heritage",
    }

    # 기술 카테고리 폴백이 단일 쿼리로 수렴하지 않도록 다양한 후보 유지
    _TECH_FALLBACK_POOL: tuple[str, ...] = (
        "smartphone screen modern minimal",
        "laptop computer workspace bright",
        "artificial intelligence neural abstract",
        "circuit board electronics close",
        "software developer code screen",
        "cloud network server datacenter",
        "wireless device bluetooth minimal",
        "wearable smartwatch fitness tech",
        "gaming controller console modern",
        "electric vehicle autonomous future",
        "drone aerial modern tech",
        "robot automation industrial future",
        "satellite space science orbit",
        "microscope science laboratory research",
        "fiber optic cable network light",
        "touchscreen display interface digital",
    )

    _BLOCKED_FALLBACK_COVERS: set[str] = {
        "https://loremflickr.com/1200/630/travel%2Cdestination%2Clandmark%2Cwalking%2Cbusan?lock=9039",
        "https://loremflickr.com/1200/630/travel%2Cdestination%2Clandmark%2Cwalking%2Cjeju?lock=6697",
    }

    def _fallback_cover_image(self, title: str, category: str, tags: list[str], slug: str) -> str:
        # for press release posts, inject institution-specific visual terms
        institution_query = ""
        for tag in tags:
            if tag in self._INSTITUTION_VISUALS:
                institution_query = self._INSTITUTION_VISUALS[tag]
                break
        keyword_input = " ".join(tags) + " " + institution_query
        query = ImageAgent.visual_query(keyword_input, category, title)
        # if still generic fallback, use institution visual directly
        if institution_query and query in ("finance policy documents",):
            query = institution_query
        # 기술 카테고리 전용 폴백: 카테고리 기본값으로 수렴하면 slug로 다양화
        if category in ("기술", "tech") and query == "technology innovation circuit abstract":
            idx = int(hashlib.md5(slug.encode("utf-8")).hexdigest()[:4], 16) % len(self._TECH_FALLBACK_POOL)
            query = self._TECH_FALLBACK_POOL[idx]
        seed_input = f"{slug}-{query}"
        seed = hashlib.md5(seed_input.encode("utf-8")).hexdigest()[:12]
        return f"https://picsum.photos/seed/{seed}/1200/630"

    @staticmethod
    def _page_href(page: int, base: str = "index.html") -> str:
        return base if page == 1 else f"page{page}.html"

    @staticmethod
    def _cat_page_href(page: int, cat_base: str) -> str:
        return cat_base if page == 1 else f"{cat_base[:-5]}-{page}.html"

    def _pagination_html(self, page: int, total_pages: int,
                         cat_base: str | None = None) -> str:
        """공통 페이지네이션 HTML. cat_base가 있으면 카테고리용, 없으면 홈용."""
        if total_pages <= 1:
            return ""
        def href(p: int) -> str:
            return self._cat_page_href(p, cat_base) if cat_base else self._page_href(p)
        nav: list[str] = []
        if page > 1:
            nav.append(f'<a class="prev" href="./{href(page-1)}">← 이전</a>')
        win_start = max(1, min(page - 3, total_pages - 6))
        win_end = min(total_pages, win_start + 6)
        pages_html = []
        for p in range(win_start, win_end + 1):
            if p == page:
                pages_html.append(f'<strong class="current">{p}</strong>')
            else:
                pages_html.append(f'<a href="./{href(p)}">{p}</a>')
        nav.append('<span class="pages">' + ' '.join(pages_html) + '</span>')
        if page < total_pages:
            nav.append(f'<a class="next" href="./{href(page+1)}">다음 →</a>')
        return '<nav class="pagination">' + "\n".join(nav) + '</nav>'

    @staticmethod
    def _strip_leading_image(markdown_text: str) -> str:
        return re.sub(r"^\s*!\[[^\]]*\]\([^)]+\)\s*", "", markdown_text, count=1)

    @staticmethod
    def _display_author(post: Post) -> str:
        if any(tag in post.tags for tag in ("보도자료", "보도기사")) and post.author:
            return f"자료: {post.author} · 편집: 브리핑웨이브"
        return "브리핑웨이브 편집팀"

    @staticmethod
    def _author_avatar(label: str) -> str:
        match = re.search(r"[가-힣A-Za-z0-9]", label)
        return match.group(0) if match else "브"

    def _write_post(self, post: Post) -> None:
        alternates = self._post_alternate_urls(post)
        cover_html = ""
        if post.cover_image:
            cover_html = f'<img class="cover" src="{html.escape(post.cover_image)}" alt="{html.escape(post.cover_image_alt)}" loading="lazy">'
        ad_slot = self._ad_slot()
        display_author = self._display_author(post)
        content = f"""
        <article class="post">
          <a class="back" href="./index.html">전체 글</a>
          {cover_html}
          <header>
            <p class="meta">{html.escape(post.category)} · {post.date:%Y-%m-%d}</p>
            <h1>{html.escape(post.title)}</h1>
            <div class="byline">
              <span class="author-avatar" aria-hidden="true">{html.escape(self._author_avatar(display_author))}</span>
              <span>{html.escape(display_author)}</span>
            </div>
            <div class="tags">{self._tag_html(post.tags)}</div>
          </header>
          {ad_slot}
          <div class="content">{post.body_html}</div>
          {ad_slot}
        </article>
        """
        self._write_html(
            f"{post.slug}.html",
            post.title,
            content,
            active=post.category,
            page_url=self._page_url(f"{post.slug}.html"),
            og_image=post.cover_image,
            alternate_urls=alternates,
        )
        # 애드센스 심사 전에는 얇은 언어별 복제 페이지를 만들지 않는다.
        # 다국어 독자 경험은 상단 번역 선택기로 제공하고, 검색 색인용 다국어 포스트는
        # 전체 본문 번역 품질을 확보한 뒤 별도 생성하는 편이 안전하다.

    def _write_localized_post_pages(self, post: Post, alternates: dict[str, str]) -> None:
        aliases = self._search_aliases(post)
        alias_text = ", ".join(aliases[:16])
        display_author = self._display_author(post)
        for lang, _label in LANGUAGE_OPTIONS:
            if lang == "ko":
                continue
            copy = LOCALIZED_POST_COPY.get(lang, LOCALIZED_POST_COPY["en"])
            direction = ' dir="rtl"' if lang == "ar" else ""
            title = f'{copy["label"]}: {post.title}'
            cover_html = ""
            if post.cover_image:
                cover_html = f'<img class="cover" src="{html.escape(post.cover_image)}" alt="{html.escape(post.cover_image_alt)}" loading="lazy">'
            content = f"""
        <article class="post localized-post"{direction}>
          <a class="back" href="../{html.escape(post.slug)}.html">{html.escape(copy["original"])}</a>
          {cover_html}
          <header>
            <p class="meta">{html.escape(copy["label"])} · {post.date:%Y-%m-%d}</p>
            <h1>{html.escape(post.title)}</h1>
            <p class="localized-notice">{html.escape(copy["notice"])}</p>
            <div class="byline">
              <span class="author-avatar" aria-hidden="true">{html.escape(self._author_avatar(display_author))}</span>
              <span>{html.escape(display_author)}</span>
            </div>
            <div class="tags">{self._tag_html(post.tags, prefix="../")}</div>
          </header>
          <section class="localized-keywords">
            <strong>{html.escape(copy["summary"])}</strong>
            <p>{html.escape(post.excerpt)}</p>
          </section>
          <section class="localized-keywords">
            <strong>{html.escape(copy["keywords"])}</strong>
            <span>{html.escape(alias_text)}</span>
          </section>
          <p><a class="read-original" href="../{html.escape(post.slug)}.html">{html.escape(copy["read"])}</a></p>
        </article>
            """
            self._write_lightweight_localized_html(
                self._localized_post_filename(post, lang),
                title,
                content,
                page_url=self._page_url(self._localized_post_filename(post, lang)),
                description=f'{copy["label"]}: {post.excerpt}',
                html_lang=lang,
                alternate_urls=alternates,
            )

    def _write_lightweight_localized_html(
        self,
        filename: str,
        title: str,
        content: str,
        page_url: str,
        description: str,
        html_lang: str,
        alternate_urls: dict[str, str],
    ) -> None:
        alternate_link_tags = "\n".join(
            f'  <link rel="alternate" hreflang="{html.escape(lang)}" href="{html.escape(url)}">'
            for lang, url in sorted(alternate_urls.items())
        )
        page = f"""<!doctype html>
<html lang="{html.escape(html_lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="{html.escape(self.site_title)}">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:url" content="{html.escape(page_url)}">
  <link rel="canonical" href="{html.escape(page_url)}">
{alternate_link_tags}
  <style>
    body{{margin:0;background:#f7f5ef;color:#232323;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.75}}
    main{{width:min(760px,100% - 32px);margin:0 auto;padding:28px 0 48px}}
    a{{color:#0f766e;text-decoration:none}}a:hover{{text-decoration:underline}}
    .post{{background:#fffdf8;border:1px solid #ded8ca;border-radius:10px;padding:22px}}
    .back{{display:inline-block;margin-bottom:14px;font-size:.9rem}}
    .cover{{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px;margin-bottom:16px}}
    .meta{{margin:0 0 6px;color:#6b675e;font-size:.86rem}}
    h1{{margin:0 0 10px;font-size:clamp(1.35rem,4vw,2rem);line-height:1.35}}
    .localized-notice,.localized-keywords{{color:#6b675e}}
    .localized-keywords{{margin:16px 0;padding:14px 16px;border:1px solid #ded8ca;border-radius:8px;background:#f7f5ef;font-size:.92rem}}
    .localized-keywords strong{{display:block;margin-bottom:6px;color:#0f766e}}
    .localized-keywords p{{margin:0}}
    .tags{{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}}
    .tag{{border:1px solid #ded8ca;border-radius:999px;padding:2px 8px;font-size:.8rem;color:#6b675e}}
    .read-original{{display:inline-flex;align-items:center;justify-content:center;min-height:38px;padding:0 14px;border-radius:999px;background:#0f766e;color:#fff;font-weight:700}}
    .read-original:hover{{text-decoration:none;filter:brightness(.94)}}
  </style>
</head>
<body>
  <main>{content}</main>
</body>
</html>
"""
        target = self.public_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")

    def _ad_slot(self) -> str:
        pub = html.escape(self.adsense_publisher_id or "ca-pub-3870943054399059")
        return f"""<div class="ad-slot">
          <ins class="adsbygoogle" style="display:block" data-ad-client="{pub}"
               data-ad-format="auto" data-full-width-responsive="true"></ins>
          <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
        </div>"""

    def _card_html(self, post: Post) -> str:
        thumb = (
            f'<a class="card-thumb" href="./{post.slug}.html">'
            f'<img class="card-img" src="{html.escape(post.cover_image)}" '
            f'alt="{html.escape(post.cover_image_alt)}" loading="lazy"></a>'
            if post.cover_image else ""
        )
        display_author = self._display_author(post)
        return f"""<article class="card">
          {thumb}
          <div class="card-body">
            <p class="meta"><span class="cat-badge">{html.escape(post.category)}</span> {post.date:%Y.%m.%d}</p>
            <h2><a href="./{post.slug}.html">{html.escape(post.title)}</a></h2>
            <p class="card-author">{html.escape(display_author)}</p>
            <p class="card-excerpt">{html.escape(post.excerpt)}</p>
            <div class="tags">{self._tag_html(post.tags[:4])}</div>
          </div>
        </article>"""

    def _write_index(self, posts: list[Post]) -> None:
        per_page = 9
        total = len(posts)
        if total == 0:
            content = """
            <section class="hero">
              <p class="hero-tagline">지금 알아야 할 소식을 빠르게 브리핑합니다</p>
            </section>
            <p class="empty">아직 발행된 글이 없습니다.</p>
            """
            self._write_html(
                "index.html",
                self.site_title,
                content,
                active="홈",
                page_url=self._page_url("index.html"),
                description=self.site_description,
            )
            return

        total_pages = (total + per_page - 1) // per_page

        for page in range(1, total_pages + 1):
            start = (page - 1) * per_page
            end = start + per_page
            page_posts = posts[start:end]
            cards = "\n".join(self._card_html(p) for p in page_posts)

            nav_html = self._pagination_html(page, total_pages)

            hero_stats = f'<p class="hero-stats">기사 {total}개 · {datetime.now():%Y.%m.%d} 업데이트</p>' if page == 1 else ""
            content = f"""
            <section class="hero">
              <p class="hero-tagline">지금 알아야 할 소식을 빠르게 브리핑합니다</p>
              {hero_stats}
            </section>
            <section class="grid">{cards}</section>
            {nav_html}
            """

            filename = "index.html" if page == 1 else f"page{page}.html"
            self._write_html(
                filename,
                self.site_title,
                content,
                active="홈",
                page_url=self._page_url(filename),
                description=self.site_description,
            )

    def _write_dashboard(self, posts: list[Post]) -> None:
        category_counts: dict[str, int] = {}
        for post in posts:
            category_counts[post.category] = category_counts.get(post.category, 0) + 1
        category_rows = "\n".join(
            f"<tr><td>{html.escape(category)}</td><td>{count}</td></tr>"
            for category, count in sorted(category_counts.items())
        )
        recent_rows = "\n".join(
            f"""
            <tr>
              <td><a href="./{post.slug}.html">{html.escape(post.title)}</a></td>
              <td>{html.escape(post.category)}</td>
              <td>{post.date:%Y-%m-%d}</td>
            </tr>
            """
            for post in posts[:20]
        )
        content = f"""
        <article class="post">
          <a class="back" href="./index.html">블로그 홈</a>
          <header>
            <p class="meta">브리핑웨이브 운영 현황</p>
            <h1>채널 대시보드</h1>
          </header>
          <section class="stats">
            <div><strong>{len(posts)}</strong><span>발행 글</span></div>
            <div><strong>{len(category_counts)}</strong><span>카테고리</span></div>
          </section>
          <h2>카테고리</h2>
          <table>
            <thead><tr><th>카테고리</th><th>글 수</th></tr></thead>
            <tbody>{category_rows or '<tr><td colspan="2">아직 글이 없습니다.</td></tr>'}</tbody>
          </table>
          <h2>최근 글</h2>
          <table>
            <thead><tr><th>제목</th><th>카테고리</th><th>날짜</th></tr></thead>
            <tbody>{recent_rows or '<tr><td colspan="3">아직 글이 없습니다.</td></tr>'}</tbody>
          </table>
        </article>
        """
        self._write_html("dashboard.html", f"{self.site_title} 운영 현황", content, active="대시보드", page_url=self._page_url("dashboard.html"))

    def _write_feed(self, posts: list[Post]) -> None:
        items = "\n".join(
            f"""
            <item>
              <title>{html.escape(post.title)}</title>
              <link>{post.slug}.html</link>
              <description>{html.escape(post.excerpt)}</description>
              <pubDate>{post.date:%a, %d %b %Y 00:00:00 +0900}</pubDate>
            </item>
            """
            for post in posts[:20]
        )
        feed = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>{html.escape(self.site_title)}</title>
    <description>오늘 꼭 확인할 생활·기술·정책 소식을 정리합니다.</description>
    <link>./</link>
    {items}
  </channel>
</rss>
"""
        (self.public_dir / "feed.xml").write_text(feed, encoding="utf-8")

    def _write_search_index(self, posts: list[Post]) -> None:
        # create a lightweight JSON index for client-side search
        items = []
        for post in posts:
            items.append(
                {
                    "title": post.title,
                    "slug": post.slug,
                    "excerpt": post.excerpt,
                    "date": post.date.strftime("%Y-%m-%d"),
                    "category": post.category,
                    "tags": post.tags,
                    "author": post.author,
                    "display_author": self._display_author(post),
                    "aliases": self._search_aliases(post),
                }
            )
        (self.public_dir / "search.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _search_aliases(post: Post) -> list[str]:
        values = [post.title, post.category, post.author, *post.tags]
        aliases: list[str] = []
        if any(tag in post.tags for tag in ("보도기사", "보도자료")) or post.slug.startswith(("krgov-", "mois-", "msit-", "mofe-", "mcst-", "khs-", "kh-")):
            aliases.extend(
                (
                    "korean government press release",
                    "south korea public agency news",
                    "official korean ministry announcement",
                    "government briefing",
                    "public institution news",
                    "韩国政府新闻稿",
                    "韓国政府プレスリリース",
                    "comunicado del gobierno coreano",
                )
            )
        for value in values:
            value_text = str(value)
            for marker, terms in SEARCH_ALIASES.items():
                if marker.lower() in value_text.lower():
                    aliases.extend(terms)
        return sorted(set(alias for alias in aliases if alias))

    def _write_search_page(self, posts: list[Post]) -> None:
        categories = sorted({post.category for post in posts})
        categories_json = json.dumps(categories, ensure_ascii=False)
        content = (
            '''
        <article class="post search-page">
          <header class="search-hero">
            <p class="meta" id="search-kicker">검색</p>
            <h1 id="search-title">글 검색</h1>
            <p class="search-help" id="search-help">키워드, 카테고리, 태그로 빠르게 찾을 수 있습니다.</p>
          </header>
          <section id="tag-overview" class="tag-overview" hidden></section>
          <section class="search-panel">
            <label for="q" class="visually-hidden">검색어 입력</label>
            <input id="q" type="search" placeholder="검색어를 입력하세요" autocomplete="off">
            <div id="suggestions" class="suggestions" aria-live="polite"></div>
            <div class="search-meta">
              <div class="category-filters" aria-label="카테고리 필터">
                <button type="button" class="chip active" data-category="">전체</button>
              </div>
              <label class="sort-label">정렬:
                <select id="sort">
                  <option value="recent">최신순</option>
                  <option value="oldest">오래된순</option>
                </select>
              </label>
            </div>
          </section>
          <div id="results-summary" class="results-summary" aria-live="polite"></div>
          <section id="results" class="search-results"></section>
        </article>
        <script>
        const categories = '''
            + categories_json
            + ''';
        const searchIndex = [];
        let activeTag = '';

        async function loadIndex(){
          const res = await fetch('./search.json');
          return await res.json();
        }

        function normalize(value){
          return value.normalize('NFKC').toLowerCase();
        }

        function escapeHtml(value){
          return String(value).replace(/[&<>"']/g, char => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
          }[char]));
        }

        function buildSuggestionText(query, items){
          if(!query && !activeTag) return '검색어를 입력하면 추천 검색어가 나타납니다.';
          const candidate = items.find(item => normalize(searchText(item)).includes(query));
          if(candidate) return `이런 검색어도 시도해보세요: ${candidate.title}`;
          return '검색 결과가 없으면 다른 키워드로 다시 시도해보세요.';
        }

        function renderTagOverview(tag){
          const overview = document.getElementById('tag-overview');
          const title = document.getElementById('search-title');
          const kicker = document.getElementById('search-kicker');
          const help = document.getElementById('search-help');
          if(!tag){
            overview.hidden = true;
            overview.innerHTML = '';
            title.textContent = '글 검색';
            kicker.textContent = '검색';
            help.textContent = '키워드, 카테고리, 태그로 빠르게 찾을 수 있습니다.';
            return;
          }

          const taggedItems = searchIndex.filter(item => (item.tags || []).includes(tag));
          const categoryCounts = taggedItems.reduce((acc, item) => {
            acc[item.category] = (acc[item.category] || 0) + 1;
            return acc;
          }, {});
          const relatedCounts = taggedItems.flatMap(item => item.tags || [])
            .filter(itemTag => itemTag !== tag)
            .reduce((acc, itemTag) => {
              acc[itemTag] = (acc[itemTag] || 0) + 1;
              return acc;
            }, {});
          const categoryText = Object.entries(categoryCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([name, count]) => `<span>${escapeHtml(name)} ${count}</span>`)
            .join('');
          const relatedTags = Object.entries(relatedCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 8)
            .map(([name, count]) => `<a class="tag related-tag" href="./search.html?tag=${encodeURIComponent(name)}">${escapeHtml(name)}<small>${count}</small></a>`)
            .join('');

          title.textContent = `#${tag}`;
          kicker.textContent = '태그 브리핑';
          help.textContent = '같은 태그로 묶인 글을 최신순으로 모았습니다.';
          overview.hidden = false;
          overview.innerHTML = `
            <div class="tag-overview-main">
              <span class="tag-count">${taggedItems.length}</span>
              <span>개의 관련 기사</span>
            </div>
            <div class="tag-overview-meta">${categoryText || '<span>분류 없음</span>'}</div>
            <div class="related-tags" aria-label="관련 태그">${relatedTags || '<span class="muted-text">함께 쓰인 태그가 아직 없습니다.</span>'}</div>
          `;
        }

        function filterResults(query, category, sortKey){
          const normalizedQuery = normalize(query);
          const matches = searchIndex.filter(item => {
            const categoryMatch = !category || item.category === category;
            const tagMatch = !activeTag || (item.tags||[]).includes(activeTag);
            if(!categoryMatch || !tagMatch) return false;
            if(!normalizedQuery) return true;
            const haystack = normalize(searchText(item));
            return haystack.includes(normalizedQuery) || item.title.split(' ').some(w=>normalize(w).startsWith(normalizedQuery));
          });
          return matches.sort((a,b)=>{
            if(sortKey === 'oldest') return new Date(a.date) - new Date(b.date);
            return new Date(b.date) - new Date(a.date);
          }).slice(0,50);
        }

        function renderResults(results){
          const resultsEl = document.getElementById('results');
          if(results.length === 0){
            resultsEl.innerHTML = '<div class="no-results"><p>검색 결과가 없습니다.</p><p class="suggestion-text">다른 검색어를 시도하거나 카테고리를 선택해 보세요.</p></div>';
            return;
	          }
	          resultsEl.innerHTML = results.map(item => `
	            <article class="card search-result">
	              <div class="result-topline">
	                <span class="cat-badge">${escapeHtml(item.category)}</span>
	                <time datetime="${escapeHtml(item.date)}">${escapeHtml(item.date)}</time>
	              </div>
	              <h2><a href="./${encodeURIComponent(item.slug)}.html">${escapeHtml(item.title)}</a></h2>
	              <p class="card-author">${escapeHtml(item.display_author || '브리핑웨이브 편집팀')}</p>
	              <p class="card-excerpt">${escapeHtml(item.excerpt)}</p>
	              <div class="tags">${(item.tags || []).map(tag=>`<a class="tag" href="./search.html?tag=${encodeURIComponent(tag)}">${escapeHtml(tag)}</a>`).join('')}</div>
	            </article>
	          `).join('');
	        }

        function renderSummary(results, query, category){
          const summary = document.getElementById('results-summary');
          const pieces = [];
          if(activeTag) pieces.push(`<strong>#${escapeHtml(activeTag)}</strong>`);
          if(query) pieces.push(`검색어 <strong>${escapeHtml(query)}</strong>`);
          if(category) pieces.push(`카테고리 <strong>${escapeHtml(category)}</strong>`);
          const scope = pieces.length ? pieces.join(' · ') : '전체 글';
          summary.innerHTML = `<span>${scope}</span><strong>${results.length}개 결과</strong>`;
        }

        function renderCategoryFilters(){
          const wrapper = document.querySelector('.category-filters');
          categories.forEach(category => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'chip';
            button.dataset.category = category;
            button.textContent = category;
            wrapper.appendChild(button);
          });
        }

        (async ()=>{
          const idx = await loadIndex();
          searchIndex.push(...idx);
          renderCategoryFilters();
          const input = document.getElementById('q');
          const suggestions = document.getElementById('suggestions');
          const sortControl = document.getElementById('sort');
          const categoryButtons = document.querySelector('.category-filters');
          let activeCategory = '';

          function update(){
            const query = input.value.trim();
            const sortKey = sortControl.value;
            const results = filterResults(query, activeCategory, sortKey);
            suggestions.textContent = buildSuggestionText(normalize(query), results);
            renderSummary(results, query, activeCategory);
            renderResults(results);
          }

          categoryButtons.addEventListener('click', event => {
            const target = event.target;
            if(target.tagName !== 'BUTTON') return;
            activeCategory = target.dataset.category || '';
            categoryButtons.querySelectorAll('button').forEach(btn => btn.classList.toggle('active', btn === target));
            update();
          });

          input.addEventListener('input', update);
          sortControl.addEventListener('change', update);

          // URL params: ?q=text and ?tag=tagname
          const urlParams = new URLSearchParams(window.location.search);
          const urlQ = urlParams.get('q');
          const urlTag = urlParams.get('tag');
          if(urlQ) input.value = urlQ;
          if(urlTag){
            activeTag = urlTag;
            renderTagOverview(activeTag);
            const badge = document.createElement('div');
            badge.className = 'tag-filter-badge';
            badge.innerHTML = '<span>태그 필터</span><strong>#' + escapeHtml(urlTag) + '</strong> <button type="button" id="clear-tag" aria-label="태그 필터 해제">×</button>';
            document.querySelector('.search-panel').appendChild(badge);
            document.getElementById('clear-tag').addEventListener('click', function(){
              activeTag = '';
              badge.remove();
              renderTagOverview('');
              const url = new URL(window.location);
              url.searchParams.delete('tag');
              window.history.replaceState({}, '', url);
              update();
            });
          } else {
            renderTagOverview('');
          }
          update();
        })();

        function searchText(item){
          return [item.title, item.excerpt, item.category].concat(item.tags || [], item.aliases || []).join(' ');
        }
        </script>
            '''
        )
        self._write_html(
            "search.html",
            f"{self.site_title} 검색",
            content,
            active="검색",
            page_url=self._page_url("search.html"),
            description="브리핑웨이브에서 원하는 글을 빠르게 찾을 수 있는 검색 페이지입니다.",
        )

    def _write_global_government_pages(self, posts: list[Post]) -> None:
        public_posts = [post for post in posts if self._is_government_post(post)]
        latest_posts = public_posts[:36]
        alternates = {lang: self._page_url(copy["filename"]) for lang, copy in GOVERNMENT_GLOBAL_PAGES.items()}
        alternates["x-default"] = self._page_url(GOVERNMENT_GLOBAL_PAGES["en"]["filename"])

        for lang, copy in GOVERNMENT_GLOBAL_PAGES.items():
            items = "\n".join(self._global_government_item_html(post, lang) for post in latest_posts)
            if not items:
                items = '<p class="empty">No government press articles are available yet.</p>'
            content = f"""
        <article class="post global-search-page">
          <header class="search-hero">
            <p class="meta">{html.escape(copy["kicker"])}</p>
            <h1>{html.escape(copy["title"])}</h1>
            <p class="search-help">{html.escape(copy["intro"])}</p>
          </header>
          <section class="global-search-terms" aria-label="search terms">
            <strong>{html.escape(copy["lang_name"])}</strong>
            <span>{html.escape(copy["terms"])}</span>
          </section>
          <section class="global-post-list">
            {items}
          </section>
        </article>
            """
            self._write_html(
                copy["filename"],
                f'{copy["title"]} - {self.site_title}',
                content,
                active="검색",
                page_url=self._page_url(copy["filename"]),
                description=copy["description"],
                html_lang=lang,
                alternate_urls=alternates,
            )

    def _global_government_item_html(self, post: Post, lang: str) -> str:
        aliases = self._search_aliases(post)
        alias_text = ", ".join(aliases[:8])
        direction = ' dir="rtl"' if lang == "ar" else ""
        return f"""
            <article class="global-post-item"{direction}>
              <p class="meta">{post.date:%Y-%m-%d} · {html.escape(post.category)}</p>
              <h2><a href="./{html.escape(post.slug)}.html">{html.escape(post.title)}</a></h2>
              <p>{html.escape(post.excerpt)}</p>
              <p class="global-aliases">{html.escape(alias_text)}</p>
            </article>
        """

    @staticmethod
    def _is_government_post(post: Post) -> bool:
        return (
            any(tag in post.tags for tag in ("보도기사", "보도자료"))
            or post.slug.startswith(("krgov-", "mois-", "msit-", "mofe-", "mcst-", "khs-", "kh-"))
        )

    def _write_category_pages(self, posts: list[Post]) -> None:
        category_posts: dict[str, list[Post]] = {}
        for post in posts:
            category_posts.setdefault(post.category, []).append(post)

        ordered_categories: list[str] = []
        for category in self.categories:
            if category not in ordered_categories:
                ordered_categories.append(category)
        for category in sorted(category_posts):
            if category not in ordered_categories:
                ordered_categories.append(category)

        per_page = 9
        for category in ordered_categories:
            all_posts = category_posts.get(category, [])
            total = len(all_posts)
            total_pages = max(1, (total + per_page - 1) // per_page)
            cat_base = self._category_page_filename(category)

            for page in range(1, total_pages + 1):
                chunk = all_posts[(page - 1) * per_page: page * per_page]
                cards = "\n".join(self._card_html(p) for p in chunk) \
                    or '<p class="empty">이 카테고리에는 아직 글이 없습니다.</p>'
                nav_html = self._pagination_html(page, total_pages, cat_base)
                stats = f" — {total}개 기사" if page == 1 else f" — {page}/{total_pages} 페이지"
                content = f"""
            <section class="hero">
              <p class="hero-tagline"><strong>{html.escape(category)}</strong>{stats}</p>
            </section>
            <section class="grid">{cards}</section>
            {nav_html}
            """
                filename = cat_base if page == 1 else f"{cat_base[:-5]}-{page}.html"
                self._write_html(
                    filename,
                    f"{category} - {self.site_title}",
                    content,
                    active=category,
                    page_url=self._page_url(filename),
                    description=f"{category} 관련 최신 글과 분석을 모아둔 페이지입니다.",
                )

    def _write_sitemap(self, posts: list[Post]) -> None:
        now = datetime.now()

        def _sitemap_loc(loc: str) -> str:
            parts = urlsplit(loc)
            encoded_path = quote(parts.path, safe="/%")
            return urlunsplit((parts.scheme, parts.netloc, encoded_path, parts.query, parts.fragment))

        def _entry(
            loc: str,
            lastmod: datetime,
            changefreq: str,
            priority: str,
            alternates: dict[str, str] | None = None,
        ) -> str:
            alternate_links = ""
            if alternates:
                alternate_links = "".join(
                    f"    <xhtml:link rel=\"alternate\" hreflang=\"{html.escape(lang)}\" href=\"{html.escape(_sitemap_loc(href))}\" />\n"
                    for lang, href in sorted(alternates.items())
                )
            return (
                f"  <url>\n"
                f"    <loc>{html.escape(_sitemap_loc(loc))}</loc>\n"
                f"{alternate_links}"
                f"    <lastmod>{lastmod:%Y-%m-%d}</lastmod>\n"
                f"    <changefreq>{changefreq}</changefreq>\n"
                f"    <priority>{priority}</priority>\n"
                f"  </url>"
            )

        def _urlset(entries: list[str]) -> str:
            return (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
                + "\n".join(entries)
                + "\n</urlset>\n"
            )

        sitemap_files: list[str] = []

        static_entries: list[str] = []
        static_entries.append(_entry(self._page_url("index.html"), now, "daily", "1.0"))
        static_entries.append(_entry(self._page_url("search.html"), now, "weekly", "0.5"))

        government_alternates = {lang: self._page_url(copy["filename"]) for lang, copy in GOVERNMENT_GLOBAL_PAGES.items()}
        government_alternates["x-default"] = self._page_url(GOVERNMENT_GLOBAL_PAGES["en"]["filename"])
        for lang, copy in GOVERNMENT_GLOBAL_PAGES.items():
            static_entries.append(_entry(
                self._page_url(copy["filename"]),
                now,
                "daily",
                "0.6",
                government_alternates,
            ))

        total_pages = (len(posts) + 8) // 9
        for page in range(2, total_pages + 1):
            static_entries.append(_entry(self._page_url(f"page{page}.html"), now, "daily", "0.9"))

        category_posts: dict[str, list[Post]] = {}
        for post in posts:
            category_posts.setdefault(post.category, []).append(post)
        per_page = 9
        for category, cposts in category_posts.items():
            cat_base = self._category_page_filename(category)
            total_cat_pages = max(1, (len(cposts) + per_page - 1) // per_page)
            for p in range(1, total_cat_pages + 1):
                fname = cat_base if p == 1 else f"{cat_base[:-5]}-{p}.html"
                static_entries.append(_entry(self._page_url(fname), now, "daily", "0.8"))

        static_name = "sitemap-static.xml"
        (self.public_dir / static_name).write_text(_urlset(static_entries), encoding="utf-8")
        sitemap_files.append(static_name)

        post_entries = []
        for post in posts:
            post_entries.append(_entry(
                self._page_url(self._localized_post_filename(post, "ko")),
                post.date,
                "monthly",
                "0.7",
                self._post_alternate_urls(post),
            ))
        posts_name = "sitemap-posts-ko.xml"
        (self.public_dir / posts_name).write_text(_urlset(post_entries), encoding="utf-8")
        sitemap_files.append(posts_name)

        sitemap_index_entries = "\n".join(
            f"  <sitemap>\n"
            f"    <loc>{html.escape(_sitemap_loc(self._page_url(filename)))}</loc>\n"
            f"    <lastmod>{now:%Y-%m-%d}</lastmod>\n"
            f"  </sitemap>"
            for filename in sitemap_files
        )
        sitemap_index = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + sitemap_index_entries
            + "\n</sitemapindex>\n"
        )
        (self.public_dir / "sitemap.xml").write_text(sitemap_index, encoding="utf-8")

    def _write_html(
        self,
        filename: str,
        title: str,
        content: str,
        active: str | None = None,
        page_url: str | None = None,
        description: str | None = None,
        og_image: str | None = None,
        html_lang: str = "ko",
        alternate_urls: dict[str, str] | None = None,
        asset_prefix: str = "./",
    ) -> None:
        gtm_id = html.escape(GTM_CONTAINER_ID)
        gtm_head = f"""  <!-- Google Tag Manager -->
  <script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
  new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
  j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
  'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
  }})(window,document,'script','dataLayer','{gtm_id}');</script>
  <!-- End Google Tag Manager -->"""
        gtm_body = f"""  <!-- Google Tag Manager (noscript) -->
  <noscript><iframe src="https://www.googletagmanager.com/ns.html?id={gtm_id}"
  height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
  <!-- End Google Tag Manager (noscript) -->"""
        ga_script = ""
        if self.ga_measurement_id:
            mid = html.escape(self.ga_measurement_id)
            ga_script = f"""
  <script async src="https://www.googletagmanager.com/gtag/js?id={mid}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{mid}');
  </script>"""

        pub = html.escape(self.adsense_publisher_id or "ca-pub-3870943054399059")
        adsense_script = (
            f'\n  <meta name="google-adsense-account" content="{pub}">'
            "\n  <script async src=\"https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-3870943054399059\"\n             crossorigin=\"anonymous\"></script>\n"
        )

        if page_url is None:
            page_url = self._page_url(filename)
        if description is None:
            description = self.site_description
        og_image_tag = ""
        if og_image:
            image_url = og_image
            if not og_image.startswith("http"):
                image_url = f"{self.site_url}/{og_image.lstrip('./')}"
            og_image_tag = f"\n  <meta property=\"og:image\" content=\"{html.escape(image_url)}\">"
        logo_url = f"{self.site_url}/favicon-512x512.png"
        structured_data = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": self.site_title,
            "url": self.site_url,
            "logo": logo_url,
        }
        structured_json = json.dumps(structured_data, ensure_ascii=False).replace("</", "<\\/")
        nav_html = self._nav_html(active, prefix=asset_prefix)
        language_switcher = self._language_switcher_html()
        language_codes_json = json.dumps([code for code, _ in LANGUAGE_OPTIONS], ensure_ascii=False)
        language_aliases_json = json.dumps(LANGUAGE_BASE_ALIASES, ensure_ascii=False)
        alternate_link_tags = ""
        if alternate_urls:
            alternate_link_tags = "\n".join(
                f'  <link rel="alternate" hreflang="{html.escape(lang)}" href="{html.escape(url)}">'
                for lang, url in sorted(alternate_urls.items())
            )
            alternate_link_tags = "\n" + alternate_link_tags

        page = f"""<!doctype html>
<html lang="{html.escape(html_lang)}">
<head>
{ga_script}
  <meta charset="utf-8">
{gtm_head}
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{html.escape(self.site_title)}">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:url" content="{html.escape(page_url)}">{og_image_tag}
  <meta name="twitter:card" content="summary_large_image">
  <meta name="naver-site-verification" content="474c602a51b653598de7203e9604b16da6381678">
  <meta name="theme-color" content="#0f766e">
  <link rel="icon" type="image/svg+xml" href="{asset_prefix}favicon.svg">
  <link rel="icon" type="image/png" sizes="48x48" href="{asset_prefix}favicon-48x48.png">
  <link rel="apple-touch-icon" sizes="180x180" href="{asset_prefix}apple-touch-icon.png">
  <link rel="manifest" href="{asset_prefix}site.webmanifest">
  <link rel="canonical" href="{html.escape(page_url)}">{alternate_link_tags}
  <link rel="stylesheet" href="{asset_prefix}style.css">
  <link rel="alternate" type="application/rss+xml" href="{asset_prefix}feed.xml">
  <script type="application/ld+json">{structured_json}</script>{adsense_script}
</head>
<body>
{gtm_body}
  <header class="site-header">
    <div class="page-shell">
      <div class="header-top">
        <a class="brand" href="{asset_prefix}index.html" aria-label="{html.escape(self.site_title)}">
          <svg class="brand-icon" width="34" height="34" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
            <rect width="32" height="32" rx="7" fill="#0f766e"/>
            <rect x="6" y="7" width="20" height="2.8" rx="1.4" fill="white" opacity="0.92"/>
            <rect x="6" y="13" width="13" height="2.8" rx="1.4" fill="white" opacity="0.92"/>
            <path d="M6 22.5 Q9.5 18 13 22.5 Q16.5 27 20 22.5 Q23.5 18 26 22.5" stroke="white" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span class="brand-wordmark">
            <span class="brand-b">브리핑</span><span class="brand-w">웨이브</span>
          </span>
        </a>
        <div class="header-search">
          <input type="search" id="header-q" placeholder="기사 검색..." autocomplete="off" aria-label="검색">
          <button class="search-btn" id="header-search-btn" type="button" aria-label="검색">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round">
              <circle cx="11" cy="11" r="7.5"/><line x1="21" y1="21" x2="16.3" y2="16.3"/>
            </svg>
          </button>
          <div id="header-results" class="header-dropdown" hidden></div>
        </div>
        {language_switcher}
      </div>
      {nav_html}
    </div>
  </header>
  <div class="page-shell">
    <main>{content}</main>
  </div>
  <footer class="site-footer">
    <div class="page-shell">
      <p>© 2024 BriefWave. All rights reserved.</p>
    </div>
  </footer>
  <script>
  (function(){{
    var q=document.getElementById('header-q'),box=document.getElementById('header-results');
    if(!q||!box)return;
    var idx=[];
    var assetPrefix='{asset_prefix}';
    fetch(assetPrefix+'search.json').then(function(r){{return r.json();}}).then(function(d){{idx=d;}}).catch(function(){{}});
    function norm(s){{return s.normalize('NFKC').toLowerCase();}}
    function searchText(item){{return [item.title,item.excerpt,item.category].concat(item.tags||[],item.aliases||[]).join(' ');}}
    function run(){{
      var val=q.value.trim();
      if(!val){{box.innerHTML='';box.hidden=true;return;}}
      var n=norm(val);
      var res=idx.filter(function(item){{
        return norm(searchText(item)).includes(n);
      }}).slice(0,6);
      if(!res.length){{box.innerHTML='<div class="hdr-item hdr-empty">검색 결과가 없습니다</div>';box.hidden=false;return;}}
      box.innerHTML=res.map(function(item){{
        return '<a class="hdr-item" href="'+assetPrefix+item.slug+'.html"><span class="hdr-title">'+item.title+'</span><span class="hdr-cat">'+item.category+'</span></a>';
      }}).join('');
      box.hidden=false;
    }}
    var btn=document.getElementById('header-search-btn');
    q.addEventListener('input',run);
    q.addEventListener('keydown',function(e){{if(e.key==='Enter'&&q.value.trim())window.location.href=assetPrefix+'search.html?q='+encodeURIComponent(q.value.trim());}});
    q.addEventListener('focus',function(){{if(q.value.trim())run();}});
    if(btn)btn.addEventListener('click',function(){{if(q.value.trim())window.location.href=assetPrefix+'search.html?q='+encodeURIComponent(q.value.trim());else q.focus();}});
    document.addEventListener('click',function(e){{if(!q.contains(e.target)&&!box.contains(e.target)&&(!btn||!btn.contains(e.target)))box.hidden=true;}});
  }})();
  </script>
  <script>
  (function(){{
    var sourceLang='ko';
    var supportedLanguages={language_codes_json};
    var languageAliases={language_aliases_json};
    var select=document.getElementById('language-select');
    function cookieValue(name){{
      var parts=document.cookie.split(';');
      for(var i=0;i<parts.length;i++){{
        var part=parts[i].trim();
        if(part.indexOf(name+'=')===0)return decodeURIComponent(part.slice(name.length+1));
      }}
      return '';
    }}
    function setCookie(name,value){{
      var maxAge='; max-age=31536000';
      var base=name+'='+encodeURIComponent(value)+'; path=/'+maxAge+'; SameSite=Lax';
      document.cookie=base;
      var host=location.hostname;
      if(host.indexOf('.')>-1){{
        document.cookie=name+'='+encodeURIComponent(value)+'; path=/; domain=.'+host+'; max-age=31536000; SameSite=Lax';
      }}
    }}
    function clearCookie(name){{
      document.cookie=name+'=; path=/; max-age=0; SameSite=Lax';
      var host=location.hostname;
      if(host.indexOf('.')>-1){{
        document.cookie=name+'=; path=/; domain=.'+host+'; max-age=0; SameSite=Lax';
      }}
    }}
    function currentLang(){{
      var raw=cookieValue('googtrans');
      var match=raw.match(/^\\/(?:auto|ko)\\/([^/]+)$/);
      return match ? match[1] : sourceLang;
    }}
    function normalizeLanguage(code){{
      if(!code)return '';
      var cleaned=String(code).trim();
      if(!cleaned)return '';
      if(supportedLanguages.indexOf(cleaned)>-1)return cleaned;
      var base=cleaned.split('-')[0];
      if(languageAliases[base])return languageAliases[base];
      for(var i=0;i<supportedLanguages.length;i++){{
        if(supportedLanguages[i].split('-')[0]===base)return supportedLanguages[i];
      }}
      return '';
    }}
    function detectPreferredLanguage(){{
      var langs=(navigator.languages&&navigator.languages.length?navigator.languages:[navigator.language||'']);
      for(var i=0;i<langs.length;i++){{
        var lang=normalizeLanguage(langs[i]);
        if(lang&&lang!==sourceLang)return lang;
      }}
      return sourceLang;
    }}
    var storedChoice=localStorage.getItem('briefwave-language-choice')||'';
    var cookieLang=currentLang();
    var initialLang=cookieLang;
    if(cookieLang===sourceLang&&!storedChoice){{
      initialLang=detectPreferredLanguage();
      if(initialLang!==sourceLang)setCookie('googtrans','/'+sourceLang+'/'+initialLang);
    }}
    if(select){{
      select.value=initialLang;
      select.addEventListener('change',function(){{
        var lang=select.value;
        localStorage.setItem('briefwave-language-choice',lang);
        if(lang===sourceLang){{
          clearCookie('googtrans');
        }}else{{
          setCookie('googtrans','/'+sourceLang+'/'+lang);
        }}
        location.reload();
      }});
    }}
    window.googleTranslateElementInit=function(){{
      if(!window.google||!window.google.translate)return;
      new window.google.translate.TranslateElement({{
        pageLanguage: sourceLang,
        includedLanguages: '{",".join(code for code, _ in LANGUAGE_OPTIONS)}',
        autoDisplay: false,
        layout: window.google.translate.TranslateElement.InlineLayout.SIMPLE
      }}, 'google_translate_element');
    }};
  }})();
  </script>
  <script src="https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit" defer></script>
</body>
</html>
"""
        target = self.public_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")

    def _write_css(self) -> None:
        css = """
:root {
  --bg: #f7f5ef;
  --ink: #232323;
  --muted: #6b675e;
  --line: #ded8ca;
  --accent: #0f766e;
  --paper: #fffdf8;
}

/* ── reset ── */
*, *::before, *::after { box-sizing: border-box; }
img { max-width: 100%; height: auto; display: block; }

/* ── base ── */
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: clamp(0.95rem, 2.5vw, 1.05rem);
  line-height: 1.75;
  -webkit-text-size-adjust: 100%;
}
main {
  width: min(1040px, 100% - 32px);
  margin: 0 auto;
  padding: 0 0 48px;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* ── hero ── */
.hero { padding: 12px 0 10px; border-bottom: 1px solid var(--line); }
.hero-tagline { margin: 0 0 4px; font-size: 1rem; color: var(--muted); word-break: keep-all; }
.hero-stats { margin: 0; font-size: 0.82rem; color: var(--muted); opacity: .7; }
.meta { margin: 0 0 6px; color: var(--muted); font-size: 0.82rem; display: flex; align-items: center; gap: 6px; }
.cat-badge { background: var(--bg); border: 1px solid var(--line); border-radius: 4px; padding: 1px 6px; font-size: 0.75rem; color: var(--muted); white-space: nowrap; }
.byline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 0.88rem;
}
.byline strong {
  color: var(--ink);
}
.author-avatar {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #e8f4ef;
  color: var(--accent);
  font-size: 0.82rem;
  font-weight: 800;
}

/* ── slim hero (index page) ── */
.hero-slim { padding: 14px 0 12px; border-bottom: 1px solid var(--line); }
.hero-tagline { margin: 0; color: var(--muted); font-size: 0.82rem; letter-spacing: 0.02em; }

.page-shell { width: min(1040px, 100% - 32px); margin: 0 auto; }
.site-header { background: var(--paper); border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 100; }
.site-header .page-shell { padding: 12px 0 0; }
.header-top { display: flex; align-items: center; gap: 14px; padding-bottom: 10px; }

/* ── brand logo ── */
.brand { display: flex; align-items: center; gap: 8px; flex-shrink: 0; text-decoration: none; line-height: 1; }
.brand:hover { text-decoration: none; }
.brand-icon { display: block; flex-shrink: 0; width: 1.75rem; height: 1.75rem; }
.brand-wordmark { display: flex; align-items: baseline; }
.brand-b { font-size: 1.25rem; font-weight: 500; color: var(--ink); letter-spacing: -0.02em; }
.brand-w { font-size: 1.25rem; font-weight: 800; color: var(--accent); letter-spacing: -0.04em; }

/* ── header search ── */
.header-search { flex: 1; position: relative; max-width: 440px; display: flex; align-items: stretch; height: 36px; }
.header-search input[type="search"] { flex: 1; min-width: 0; height: 36px; padding: 0 14px; border: 1px solid var(--line); border-right: none; border-radius: 999px 0 0 999px; background: var(--paper); font-size: 0.88rem; color: var(--ink); outline: none; transition: border-color .2s; -webkit-appearance: none; box-sizing: border-box; }
.header-search input[type="search"]:focus { border-color: var(--accent); }
.header-search input[type="search"]:focus + .search-btn { border-color: var(--accent); background: var(--accent); color: #fff; }
.search-btn { flex-shrink: 0; display: flex; align-items: center; justify-content: center; width: 42px; height: 36px; border: 1px solid var(--line); border-left: none; border-radius: 0 999px 999px 0; background: var(--bg); color: var(--muted); cursor: pointer; transition: background .2s, color .2s, border-color .2s; padding: 0; }
.search-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
.header-dropdown { position: absolute; top: calc(100% + 6px); left: 0; right: 0; background: var(--paper); border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,.1); z-index: 200; overflow: hidden; }
.hdr-item { display: flex; align-items: center; gap: 10px; padding: 10px 16px; color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--line); transition: background .15s; font-size: 0.88rem; }
.hdr-item:last-child { border-bottom: none; }
.hdr-item:hover { background: var(--bg); }
.hdr-title { flex: 1; line-height: 1.4; word-break: keep-all; }
.hdr-cat { color: var(--muted); font-size: 0.75rem; flex-shrink: 0; }
.hdr-empty { color: var(--muted); justify-content: center; }
.language-switcher { flex-shrink: 0; position: relative; height: 36px; }
.language-switcher select {
  width: 116px;
  height: 36px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--paper);
  color: var(--ink);
  font: inherit;
  font-size: 0.82rem;
  padding: 0 30px 0 12px;
  cursor: pointer;
  outline: none;
}
.language-switcher select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(15,118,110,.12); }
.translate-host {
  position: absolute;
  left: -9999px;
  top: auto;
  width: 1px;
  height: 1px;
  overflow: hidden;
}
body > .skiptranslate,
.goog-te-banner-frame,
.goog-te-balloon-frame { display: none !important; }
body { top: 0 !important; }
.dashboard-link { flex-shrink: 0; color: var(--muted); font-size: 0.85rem; padding: 7px 14px; border: 1px solid var(--line); border-radius: 999px; white-space: nowrap; transition: background .2s, color .2s, border-color .2s; }
.dashboard-link:hover, .dashboard-link.active { background: var(--accent); color: #fff; border-color: var(--accent); text-decoration: none; }

/* category tab nav */
.site-nav { display: flex; gap: 0; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
.site-nav::-webkit-scrollbar { display: none; }
.site-nav a { color: var(--muted); padding: 9px 18px; font-size: 0.9rem; font-weight: 500; border-bottom: 2px solid transparent; transition: color .2s, border-color .2s; white-space: nowrap; text-decoration: none; display: block; }
.site-nav a:hover { color: var(--ink); }
.site-nav a.active { color: var(--accent); border-bottom-color: var(--accent); }

/* clickable tags */
a.tag { text-decoration: none; }
a.tag:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

/* tag filter badge */
.tag-filter-badge { display: inline-flex; align-items: center; gap: 8px; background: #123b36; color: #fff; border-radius: 999px; padding: 7px 12px; font-size: 0.85rem; margin-top: 12px; box-shadow: 0 8px 18px rgba(15,118,110,.16); }
.tag-filter-badge span { color: rgba(255,255,255,.72); font-size: 0.78rem; }
.tag-filter-badge button { width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; background: rgba(255,255,255,.14); border: none; border-radius: 999px; color: #fff; cursor: pointer; font-size: 1rem; padding: 0; line-height: 1; }
.tag-filter-badge button:hover { background: rgba(255,255,255,.24); }

/* global government search pages */
.global-search-page { max-width: 920px; margin: 0 auto; }
.global-search-terms {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 18px 0 8px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  color: var(--muted);
  font-size: 0.9rem;
}
.global-search-terms strong { color: var(--accent); }
.global-post-list { display: grid; gap: 12px; margin-top: 16px; }
.global-post-item {
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
}
.global-post-item h2 {
  margin: 0 0 8px;
  font-size: clamp(1rem, 2.6vw, 1.16rem);
  line-height: 1.42;
  word-break: keep-all;
}
.global-post-item p { margin: 0 0 8px; color: var(--muted); font-size: 0.9rem; line-height: 1.65; }
.global-post-item .global-aliases { margin-bottom: 0; color: #7a7468; font-size: 0.78rem; }
.localized-notice {
  margin: 10px 0 14px;
  color: var(--muted);
  font-size: 0.95rem;
  line-height: 1.7;
}
.localized-keywords {
  margin: 16px 0 20px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  color: var(--muted);
  font-size: 0.86rem;
}
.localized-keywords strong {
  display: block;
  margin-bottom: 6px;
  color: var(--accent);
}
.localized-keywords p { margin: 0; color: var(--muted); }
.read-original {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 0 14px;
  border-radius: 999px;
  background: var(--accent);
  color: #fff;
  font-weight: 700;
  font-size: 0.9rem;
}
.read-original:hover { text-decoration: none; filter: brightness(.94); }

/* footer */
.site-footer { border-top: 1px solid var(--line); background: var(--paper); margin-top: 32px; }
.site-footer .page-shell { padding: 24px 0; text-align: center; color: var(--muted); font-size: 0.82rem; }

/* ── index grid ── */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(300px, 100%), 1fr));
  gap: 16px;
  padding-top: 14px;
}
.card {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: box-shadow .2s, transform .18s;
}
.card:hover { box-shadow: 0 6px 28px rgba(0,0,0,.09); transform: translateY(-3px); }
.card-body { padding: 14px 16px 16px; flex: 1; display: flex; flex-direction: column; }
.card h2 { margin: 0 0 8px; font-size: clamp(0.98rem, 2.8vw, 1.1rem); line-height: 1.38; word-break: keep-all; }
.card h2 a { color: var(--ink); }
.card h2 a:hover { color: var(--accent); text-decoration: none; }
.card-author { margin: -3px 0 8px; color: var(--muted); font-size: 0.78rem; line-height: 1.4; }
.card-excerpt { margin: 0 0 12px; font-size: 0.87rem; color: var(--muted); line-height: 1.55;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; flex: 1; }

/* ── card thumbnail ── */
.card-thumb { display: block; }
.card-img {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  object-position: center center;
  border-radius: 0;
  display: block;
  margin: 0;
}

/* ── tags ── */
.tags { display: flex; flex-wrap: wrap; gap: 5px; }
.tag {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 2px 8px;
  color: var(--muted);
  font-size: 0.75rem;
  white-space: nowrap;
}

/* ── post ── */
.post {
  max-width: 720px;
  margin: 0 auto;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: clamp(16px, 4vw, 32px);
}
.post h1 {
  margin: 8px 0 14px;
  font-size: clamp(1.4rem, 5vw, 2.4rem);
  line-height: 1.2;
  word-break: keep-all;
}
.back { display: inline-block; margin-bottom: 20px; color: var(--muted); font-size: 0.9rem; }

/* ── search and tag pages ── */
.search-page {
  max-width: 920px;
  border-radius: 12px;
}
.search-hero {
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
}
.search-hero h1 {
  margin-bottom: 8px;
}
.search-panel {
  margin-top: 18px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #faf8f1;
}
.search-panel input[type="search"] {
  width: 100%;
  height: 44px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  color: var(--ink);
  font: inherit;
  padding: 0 14px;
  outline: none;
  -webkit-appearance: none;
}
.search-panel input[type="search"]:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(15,118,110,.12);
}
.suggestions {
  min-height: 22px;
  margin-top: 8px;
  color: var(--muted);
  font-size: 0.85rem;
}
.search-meta {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-top: 12px;
}
.category-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.chip {
  min-height: 32px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--paper);
  color: var(--muted);
  padding: 0 12px;
  cursor: pointer;
  font: inherit;
  font-size: 0.85rem;
}
.chip:hover,
.chip.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.sort-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: 0.85rem;
  white-space: nowrap;
}
.sort-label select {
  height: 32px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  color: var(--ink);
  padding: 0 8px;
}
.tag-overview {
  margin-top: 18px;
  padding: 18px;
  border: 1px solid rgba(15,118,110,.22);
  border-radius: 12px;
  background: linear-gradient(135deg, #f2fbf8 0%, #fffdf8 58%, #f7f1df 100%);
}
.tag-overview-main {
  display: flex;
  align-items: baseline;
  gap: 8px;
  color: var(--ink);
}
.tag-count {
  color: var(--accent);
  font-size: 2.2rem;
  font-weight: 800;
  line-height: 1;
}
.tag-overview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 12px;
}
.tag-overview-meta span {
  border: 1px solid rgba(15,118,110,.2);
  border-radius: 999px;
  background: rgba(255,255,255,.66);
  color: #33524d;
  padding: 3px 9px;
  font-size: 0.8rem;
}
.related-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 14px;
}
.related-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--paper);
}
.related-tag small {
  color: var(--accent);
  font-size: 0.68rem;
}
.muted-text {
  color: var(--muted);
  font-size: 0.86rem;
}
.results-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin: 18px 0 10px;
  color: var(--muted);
  font-size: 0.9rem;
}
.results-summary strong {
  color: var(--ink);
}
.search-results {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}
.search-result {
  border-radius: 10px;
  padding: 16px;
}
.search-result h2 {
  margin-top: 10px;
}
.result-topline {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: 0.82rem;
}
.no-results {
  border: 1px dashed var(--line);
  border-radius: 10px;
  padding: 24px;
  text-align: center;
  color: var(--muted);
  background: #faf8f1;
}
.suggestion-text {
  margin-bottom: 0;
  font-size: 0.9rem;
}

/* ── cover image ── */
.cover {
  display: block;
  margin: 0 auto 20px;
  width: 100%;
  max-width: 720px;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  object-position: center center;
  border-radius: 8px;
}

/* ── post content ── */
.content { margin-top: 24px; }
.content h2 { margin-top: 28px; font-size: clamp(1.1rem, 3.5vw, 1.4rem); line-height: 1.3; word-break: keep-all; }
.content h3 { font-size: clamp(1rem, 3vw, 1.2rem); }
.content p { margin: 0 0 1em; }
.content ul, .content ol { padding-left: 1.4em; }
.content li { margin-bottom: 0.3em; }

/* ── table: scrollable on mobile ── */
.content .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 16px 0; }

/* center images inside post content */
.content img { display: block; margin: 16px auto; max-width: 100%; height: auto; }
.content table { width: 100%; min-width: 360px; border-collapse: collapse; font-size: 0.9rem; }
.content th, .content td { border: 1px solid var(--line); padding: 8px 10px; text-align: left; white-space: nowrap; }
.content th { background: #ece7da; }

/* ── ad slot ── */
.ad-slot { margin: 20px 0; overflow: hidden; }

/* ── dashboard ── */
.empty { padding: 24px 0; color: var(--muted); }
.stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 20px 0; }
.stats div { border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #faf7ef; }
.stats strong { display: block; font-size: 1.8rem; line-height: 1.1; }
.stats span { color: var(--muted); font-size: 0.85rem; }

/* ── mobile ── */
@media (max-width: 480px) {
  main { width: 100%; padding: 0 0 48px; }
  .site-header .page-shell { padding: 10px 16px 0; }
  .header-top { flex-wrap: wrap; gap: 8px; padding-bottom: 8px; }
  .header-search { order: 3; flex: none; width: 100%; max-width: 100%; height: 38px; }
  .header-search input[type="search"] { height: 38px; }
  .search-btn { height: 38px; }
  .language-switcher { margin-left: auto; height: 34px; }
  .language-switcher select { width: 104px; height: 34px; font-size: 0.78rem; }
  .site-nav { padding: 0 4px; }
  .hero { padding: 10px 16px 8px; }
  .grid { grid-template-columns: 1fr; gap: 10px; padding: 10px 12px 0; }
  .card { border-radius: 10px; }
  .card-body { padding: 12px 14px 14px; }
	  .post { border-radius: 0; border-left: none; border-right: none; padding: 16px; }
	  .search-page { max-width: none; }
	  .search-panel { padding: 14px; }
	  .search-meta { flex-direction: column; align-items: stretch; }
	  .category-filters { width: 100%; }
	  .sort-label { justify-content: space-between; width: 100%; }
	  .sort-label select { max-width: 150px; }
	  .tag-overview { padding: 16px; }
	  .results-summary { align-items: flex-start; flex-direction: column; gap: 4px; }
	  .cover { border-radius: 0; aspect-ratio: 16 / 9; object-fit: cover; object-position: center center; max-height: 200px; }
  .content table { font-size: 0.82rem; }
  .content th, .content td { padding: 6px 8px; }
  .stats { grid-template-columns: 1fr; }
}

@media (min-width: 481px) and (max-width: 768px) {
  .cover { max-height: 280px; }
}
"""
        extra = (
            "\n.pagination { display:flex; justify-content:center; align-items:center; gap:4px; margin-top:32px; margin-bottom:8px; flex-wrap:nowrap; overflow-x:auto; -webkit-overflow-scrolling:touch; padding:4px 12px 8px; scrollbar-width:none; }"
            " .pagination::-webkit-scrollbar { display:none; }"
            " .pagination a,.pagination .current { min-width:34px; height:34px; display:inline-flex; align-items:center; justify-content:center; border-radius:8px; font-size:0.875rem; flex-shrink:0; }"
            " .pagination a { color:var(--accent); border:1px solid var(--line); text-decoration:none; transition:background .15s,color .15s; }"
            " .pagination a:hover { background:var(--accent); color:#fff; border-color:var(--accent); }"
            " .pagination .current { background:var(--accent); color:#fff; font-weight:700; border:1px solid var(--accent); }"
            " .pagination .prev,.pagination .next { padding:0 10px; min-width:auto; font-size:0.8rem; border-radius:8px; white-space:nowrap; }"
            " .pagination .pages { display:contents; }"
        )
        (self.public_dir / "style.css").write_text((css.strip() + "\n" + extra).lstrip() + "\n", encoding="utf-8")

    def _write_robots(self) -> None:
        content = (
            "User-agent: *\n"
            "Allow: /\n"
            f"Sitemap: {self.site_url}/sitemap.xml\n"
        )
        (self.public_dir / "robots.txt").write_text(content, encoding="utf-8")

    def _write_favicon(self) -> None:
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="7" fill="#0f766e"/>
  <rect x="6" y="7" width="20" height="2.8" rx="1.4" fill="white" opacity="0.92"/>
  <rect x="6" y="13" width="13" height="2.8" rx="1.4" fill="white" opacity="0.92"/>
  <path d="M6 22.5 Q9.5 18 13 22.5 Q16.5 27 20 22.5 Q23.5 18 26 22.5" stroke="white" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""
        (self.public_dir / "favicon.svg").write_text(svg, encoding="utf-8")
        for size, name in (
            (48, "favicon-48x48.png"),
            (180, "apple-touch-icon.png"),
            (192, "icon-192x192.png"),
            (512, "favicon-512x512.png"),
        ):
            (self.public_dir / name).write_bytes(self._brand_png(size))
        manifest = {
            "name": self.site_title,
            "short_name": self.site_title,
            "icons": [
                {"src": "./icon-192x192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "./favicon-512x512.png", "sizes": "512x512", "type": "image/png"},
            ],
            "theme_color": "#0f766e",
            "background_color": "#0f766e",
            "display": "standalone",
        }
        (self.public_dir / "site.webmanifest").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _brand_png(size: int) -> bytes:
        teal = (15, 118, 110, 255)
        white = (255, 255, 255, 238)
        transparent = (0, 0, 0, 0)
        radius = max(7, size // 5)
        pixels: list[list[tuple[int, int, int, int]]] = []

        def inside_round_rect(x: int, y: int, w: int, h: int, r: int) -> bool:
            if r <= x < w - r or r <= y < h - r:
                return 0 <= x < w and 0 <= y < h
            cx = r if x < r else w - r - 1
            cy = r if y < r else h - r - 1
            return (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2

        for y in range(size):
            row = []
            for x in range(size):
                row.append(teal if inside_round_rect(x, y, size, size, radius) else transparent)
            pixels.append(row)

        def fill_rect(x0: int, y0: int, w: int, h: int, color: tuple[int, int, int, int]) -> None:
            rr = max(1, h // 2)
            for yy in range(y0, y0 + h):
                for xx in range(x0, x0 + w):
                    if 0 <= xx < size and 0 <= yy < size and inside_round_rect(xx - x0, yy - y0, w, h, rr):
                        pixels[yy][xx] = color

        def draw_disc(cx: int, cy: int, r: int, color: tuple[int, int, int, int]) -> None:
            for yy in range(cy - r, cy + r + 1):
                for xx in range(cx - r, cx + r + 1):
                    if 0 <= xx < size and 0 <= yy < size and (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2:
                        pixels[yy][xx] = color

        def draw_line(x1: int, y1: int, x2: int, y2: int, width: int, color: tuple[int, int, int, int]) -> None:
            steps = max(abs(x2 - x1), abs(y2 - y1), 1)
            for step in range(steps + 1):
                t = step / steps
                x = round(x1 + (x2 - x1) * t)
                y = round(y1 + (y2 - y1) * t)
                draw_disc(x, y, max(1, width // 2), color)

        fill_rect(size * 6 // 32, size * 7 // 32, size * 20 // 32, max(3, size * 3 // 32), white)
        fill_rect(size * 6 // 32, size * 13 // 32, size * 13 // 32, max(3, size * 3 // 32), white)
        points = [
            (size * 6 // 32, size * 23 // 32),
            (size * 10 // 32, size * 19 // 32),
            (size * 14 // 32, size * 23 // 32),
            (size * 18 // 32, size * 27 // 32),
            (size * 22 // 32, size * 23 // 32),
            (size * 26 // 32, size * 23 // 32),
        ]
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            draw_line(x1, y1, x2, y2, max(3, size * 3 // 32), white)

        raw = b"".join(b"\x00" + b"".join(bytes(px) for px in row) for row in pixels)
        def chunk(kind: bytes, data: bytes) -> bytes:
            import binascii
            payload = kind + data
            return struct.pack(">I", len(data)) + payload + struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)

        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )

    def _write_cname(self) -> None:
      if self.custom_domain:
        (self.public_dir / "CNAME").write_text(self.custom_domain.strip() + "\n", encoding="utf-8")

      # write ads.txt so AdSense crawler can find publisher info at site root
      pub = (self.adsense_publisher_id or "ca-pub-3870943054399059").strip()
      ads_content = f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n"
      (self.public_dir / "ads.txt").write_text(ads_content, encoding="utf-8")

      # ensure search.json is present even if no posts
      if not (self.public_dir / "search.json").exists():
        (self.public_dir / "search.json").write_text("[]", encoding="utf-8")

    def _copy_assets(self) -> None:
        assets_dir = self.posts_dir.parent / "assets"
        if not assets_dir.exists():
            return
        target_dir = self.public_dir / "assets"
        target_dir.mkdir(parents=True, exist_ok=True)
        for path in assets_dir.rglob("*"):
            if path.is_file():
                dest = target_dir / path.relative_to(assets_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)

    @staticmethod
    def _parse_date(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now()

    @staticmethod
    def _excerpt(markdown_text: str) -> str:
        text = re.sub(r"```.*?```", "", markdown_text, flags=re.S)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"[\n#>*_|`-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:160] + ("..." if len(text) > 160 else "")

    @staticmethod
    def _tag_html(tags: list[str], prefix: str = "./") -> str:
        return "".join(f'<a class="tag" href="{prefix}search.html?tag={quote(tag)}">{html.escape(tag)}</a>' for tag in tags)

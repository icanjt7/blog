from __future__ import annotations

import html
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import markdown
import yaml


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
      self._write_category_pages(posts)

      # self._write_dashboard(posts)  # 관리자 전용 — 일반 사용자에게 노출하지 않음
      self._write_feed(posts)
      self._write_sitemap(posts)
      self._write_css()
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
            _, frontmatter, body = raw.split("---", 2)
            meta = yaml.safe_load(frontmatter) or {}
        title = str(meta.get("title") or path.stem)
        date = self._parse_date(str(meta.get("date") or datetime.now().isoformat()))
        _cat_map = {"tech": "기술", "living": "생활", "finance": "정책", "local": "핫이슈"}
        category = str(meta.get("category") or "생활")
        category = _cat_map.get(category, category)
        tags = [str(tag) for tag in meta.get("tags", [])]
        body_html = markdown.markdown(
            body,
            extensions=["tables", "fenced_code", "toc"],
            output_format="html5",
        )
        # wrap tables for horizontal scroll on mobile
        body_html = body_html.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
        excerpt = self._excerpt(body)
        return Post(
            title=title,
            date=date,
            category=category,
            tags=tags,
            slug=path.stem,
            excerpt=excerpt,
            body_html=body_html,
            cover_image=str(meta.get("cover_image") or ""),
            cover_image_alt=str(meta.get("cover_image_alt") or title),
            author=str(meta.get("author") or self._author_for_slug(path.stem)),
        )

    def _slugify(self, value: str) -> str:
        normalized = value.strip().lower()
        return re.sub(r"[^\w가-힣-]+", "-", normalized).strip("-") or "category"

    def _page_url(self, filename: str) -> str:
        if filename == "index.html":
            return self.site_url + "/"
        return f"{self.site_url}/{filename}"

    def _nav_html(self, active: str | None = None) -> str:
        items = [
            '<a href="./index.html" class="' + ("active" if active == "홈" else "") + '">홈</a>'
        ]
        for category in self.categories:
            href = f"./category-{self._slugify(category)}.html"
            active_class = "active" if active == category else ""
            items.append(f'<a href="{href}" class="{active_class}">{html.escape(category)}</a>')
        return '<nav class="site-nav">' + "".join(items) + '</nav>'

    def _category_page_filename(self, category: str) -> str:
        return f"category-{self._slugify(category)}.html"

    @staticmethod
    def _author_for_slug(slug: str) -> str:
        digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()
        return AUTHOR_NAMES[int(digest[:8], 16) % len(AUTHOR_NAMES)]

    def _write_post(self, post: Post) -> None:
        cover_html = ""
        if post.cover_image:
            cover_html = f'<img class="cover" src="{html.escape(post.cover_image)}" alt="{html.escape(post.cover_image_alt)}" loading="lazy">'
        ad_slot = self._ad_slot()
        content = f"""
        <article class="post">
          <a class="back" href="./index.html">전체 글</a>
          {cover_html}
          <header>
            <p class="meta">{html.escape(post.category)} · {post.date:%Y-%m-%d}</p>
            <h1>{html.escape(post.title)}</h1>
            <div class="byline">
              <span class="author-avatar" aria-hidden="true">{html.escape(post.author[:1])}</span>
              <span><strong>{html.escape(post.author)}</strong> 기자</span>
            </div>
            <div class="tags">{self._tag_html(post.tags)}</div>
          </header>
          {ad_slot}
          <div class="content">{post.body_html}</div>
          {ad_slot}
        </article>
        """
        self._write_html(f"{post.slug}.html", post.title, content, active=post.category, page_url=self._page_url(f"{post.slug}.html"))

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
        return f"""<article class="card">
          {thumb}
          <div class="card-body">
            <p class="meta"><span class="cat-badge">{html.escape(post.category)}</span> {post.date:%Y.%m.%d}</p>
            <h2><a href="./{post.slug}.html">{html.escape(post.title)}</a></h2>
            <p class="card-author">by {html.escape(post.author)} 기자</p>
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

            # pagination links
            nav_items: list[str] = []
            if page > 1:
                prev_href = "index.html" if page - 1 == 1 else f"page{page-1}.html"
                nav_items.append(f'<a class="prev" href="./{prev_href}">← 이전</a>')
            pages_html = []
            for p in range(1, total_pages + 1):
                href = "index.html" if p == 1 else f"page{p}.html"
                if p == page:
                    pages_html.append(f'<strong class="current">{p}</strong>')
                else:
                    pages_html.append(f'<a href="./{href}">{p}</a>')
            nav_items.append('<span class="pages">' + ' '.join(pages_html) + '</span>')
            if page < total_pages:
                nav_items.append(f'<a class="next" href="./page{page+1}.html">다음 →</a>')
            nav_html = '<nav class="pagination">' + "\n".join(nav_items) + '</nav>'

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
                }
            )
        (self.public_dir / "search.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

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
          const candidate = items.find(item => normalize(item.title).includes(query) || normalize((item.tags||[]).join(' ')).includes(query));
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
            const haystack = normalize([item.title, item.excerpt, item.category, ...(item.tags || [])].join(' '));
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
	              <p class="card-author">by ${escapeHtml(item.author || '브리핑웨이브')} 기자</p>
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

        for category in ordered_categories:
            page_posts = category_posts.get(category, [])
            cards = "\n".join(self._card_html(p) for p in page_posts) \
                or '<p class="empty">이 카테고리에는 아직 글이 없습니다.</p>'
            content = f"""
            <section class="hero">
              <p class="hero-tagline"><strong>{html.escape(category)}</strong> — {len(page_posts)}개 기사</p>
            </section>
            <section class="grid">{cards}</section>
            """
            filename = self._category_page_filename(category)
            self._write_html(
                filename,
                f"{category} - {self.site_title}",
                content,
                active=category,
                page_url=self._page_url(filename),
                description=f"{category} 관련 최신 글과 분석을 모아둔 페이지입니다.",
            )

    def _write_sitemap(self, posts: list[Post]) -> None:
        urls: list[tuple[str, datetime]] = []
        urls.append((self._page_url("index.html"), datetime.now()))
        urls.append((self._page_url("search.html"), datetime.now()))

        total_pages = (len(posts) + 8) // 9
        for page in range(2, total_pages + 1):
            urls.append((self._page_url(f"page{page}.html"), datetime.now()))

        category_posts: dict[str, list[Post]] = {}
        for post in posts:
            category_posts.setdefault(post.category, []).append(post)
        for category in category_posts:
            filename = self._category_page_filename(category)
            urls.append((self._page_url(filename), datetime.now()))

        for post in posts:
            urls.append((self._page_url(f"{post.slug}.html"), post.date))

        sitemap_items = "\n".join(
            f"  <url>\n    <loc>{html.escape(url)}</loc>\n    <lastmod>{modified:%Y-%m-%d}</lastmod>\n  </url>"
            for url, modified in urls
        )
        sitemap = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
{sitemap_items}
</urlset>"""
        (self.public_dir / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    def _write_html(
        self,
        filename: str,
        title: str,
        content: str,
        active: str | None = None,
        page_url: str | None = None,
        description: str | None = None,
        og_image: str | None = None,
    ) -> None:
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
        nav_html = self._nav_html(active)

        page = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{html.escape(self.site_title)}">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:url" content="{html.escape(page_url)}">{og_image_tag}
  <meta name="twitter:card" content="summary_large_image">
  <link rel="canonical" href="{html.escape(page_url)}">
  <link rel="stylesheet" href="./style.css">
  <link rel="alternate" type="application/rss+xml" href="./feed.xml">{ga_script}{adsense_script}
</head>
<body>
  <header class="site-header">
    <div class="page-shell">
      <div class="header-top">
        <a class="brand" href="./index.html" aria-label="{html.escape(self.site_title)}">
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
    fetch('./search.json').then(function(r){{return r.json();}}).then(function(d){{idx=d;}}).catch(function(){{}});
    function norm(s){{return s.normalize('NFKC').toLowerCase();}}
    function run(){{
      var val=q.value.trim();
      if(!val){{box.innerHTML='';box.hidden=true;return;}}
      var n=norm(val);
      var res=idx.filter(function(item){{
        return norm([item.title,item.excerpt].concat(item.tags||[]).join(' ')).includes(n);
      }}).slice(0,6);
      if(!res.length){{box.innerHTML='<div class="hdr-item hdr-empty">검색 결과가 없습니다</div>';box.hidden=false;return;}}
      box.innerHTML=res.map(function(item){{
        return '<a class="hdr-item" href="./'+item.slug+'.html"><span class="hdr-title">'+item.title+'</span><span class="hdr-cat">'+item.category+'</span></a>';
      }}).join('');
      box.hidden=false;
    }}
    var btn=document.getElementById('header-search-btn');
    q.addEventListener('input',run);
    q.addEventListener('keydown',function(e){{if(e.key==='Enter'&&q.value.trim())window.location.href='./search.html?q='+encodeURIComponent(q.value.trim());}});
    q.addEventListener('focus',function(){{if(q.value.trim())run();}});
    if(btn)btn.addEventListener('click',function(){{if(q.value.trim())window.location.href='./search.html?q='+encodeURIComponent(q.value.trim());else q.focus();}});
    document.addEventListener('click',function(e){{if(!q.contains(e.target)&&!box.contains(e.target)&&(!btn||!btn.contains(e.target)))box.hidden=true;}});
  }})();
  </script>
</body>
</html>
"""
        (self.public_dir / filename).write_text(page, encoding="utf-8")

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
            "\n.pagination { display:flex; justify-content:center; align-items:center; gap:8px; margin-top:28px; flex-wrap:wrap; }"
            " .pagination a,.pagination .current { min-width:36px; height:36px; display:inline-flex; align-items:center; justify-content:center; border-radius:8px; font-size:0.9rem; }"
            " .pagination a { color:var(--accent); border:1px solid var(--line); text-decoration:none; transition:background .2s,color .2s; }"
            " .pagination a:hover { background:var(--accent); color:#fff; border-color:var(--accent); }"
            " .pagination .current { background:var(--accent); color:#fff; font-weight:700; border:1px solid var(--accent); }"
            " .pagination .prev,.pagination .next { padding:0 14px; min-width:auto; }"
        )
        (self.public_dir / "style.css").write_text((css.strip() + "\n" + extra).lstrip() + "\n", encoding="utf-8")

    def _write_cname(self) -> None:
      if self.custom_domain:
        (self.public_dir / "CNAME").write_text(self.custom_domain.strip() + "\n", encoding="utf-8")

      # write ads.txt so AdSense crawler can find publisher info at site root
      pub = (self.adsense_publisher_id or "ca-pub-3870943054399059").strip()
      ads_content = f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n"
      (self.public_dir / "ads.txt").write_text(ads_content, encoding="utf-8")

      # write a permissive robots.txt to ensure crawlers can access the site
      robots = "User-agent: *\nAllow: /\n"
      (self.public_dir / "robots.txt").write_text(robots, encoding="utf-8")
      # ensure search.json is present even if no posts
      if not (self.public_dir / "search.json").exists():
        (self.public_dir / "search.json").write_text("[]", encoding="utf-8")

    def _copy_assets(self) -> None:
        assets_dir = self.posts_dir.parent / "assets"
        if not assets_dir.exists():
            return
        target_dir = self.public_dir / "assets"
        target_dir.mkdir(parents=True, exist_ok=True)
        for path in assets_dir.iterdir():
            if path.is_file():
                shutil.copy2(path, target_dir / path.name)

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
    def _tag_html(tags: list[str]) -> str:
        return "".join(f'<a class="tag" href="./search.html?tag={quote(tag)}">{html.escape(tag)}</a>' for tag in tags)

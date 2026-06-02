from blog_agent.config import load_settings
from blog_agent.publishers import build_publisher
from blog_agent.models import Draft, Topic

settings = load_settings()
publisher = build_publisher(settings)

topic = Topic(keyword="테스트 게시물", title_hint="테스트", category="tech")

draft = Draft(
    topic=topic,
    title="테스트 포스팅 - 자동 게시",
    slug="test-auto-post",
    excerpt="이 포스팅은 자동화 테스트용입니다.",
    body_markdown="## 자동 게시 테스트\n\n이 포스팅은 자동 게시 기능을 확인하기 위한 테스트입니다.",
    tags=["테스트", "자동화"],
)

result = publisher.publish(draft)
print(result.model_dump())

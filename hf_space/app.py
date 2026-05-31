from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

import gradio as gr
from openai import OpenAI

from blog_agent.config import load_settings
from blog_agent.pipeline import BlogPipeline


def generate_drafts(count: int, min_quality: int) -> tuple[str, str]:
    settings = load_settings()
    settings.output_dir = Path(tempfile.mkdtemp(prefix="blog-agent-posts-"))
    settings.state_dir = Path(tempfile.mkdtemp(prefix="blog-agent-state-"))
    settings.publisher = "markdown"
    result = BlogPipeline(settings).run(count=int(count), dry_run=True, min_quality=float(min_quality))
    if not result.drafts:
        return "생성된 초안이 없습니다.", ""

    summary_lines = []
    first_body = ""
    for idx, draft in enumerate(result.drafts, start=1):
        summary_lines.append(
            f"{idx}. {draft.title}\n"
            f"   - keyword: {draft.topic.keyword}\n"
            f"   - category: {draft.topic.category}\n"
            f"   - quality: {draft.quality_score:.1f}\n"
            f"   - notes: {', '.join(draft.review_notes) if draft.review_notes else 'none'}"
        )
        if idx == 1:
            first_body = f"# {draft.title}\n\n{draft.body_markdown}"
    return "\n\n".join(summary_lines), first_body


def build_image_prompt(title: str, body: str, style: str) -> str:
    title = title.strip() or "한국어 정보성 블로그 대표 이미지"
    body_hint = " ".join(body.split())[:500]
    return (
        f"Create a clean editorial blog cover image for a Korean informational article.\n"
        f"Title/theme: {title}\n"
        f"Context: {body_hint}\n"
        f"Style: {style}\n"
        f"Requirements: no readable text, no logos, no brand marks, natural lighting, "
        f"high trust, useful information design mood, 16:9 composition."
    )


def generate_image(prompt: str) -> tuple[str | None, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "OPENAI_API_KEY Space Secret이 필요합니다."

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_IMAGE_TEXT_MODEL", "gpt-5")
    response = client.responses.create(
        model=model,
        input=prompt,
        tools=[{"type": "image_generation", "action": "generate"}],
    )
    image_base64 = None
    for item in response.output:
        if getattr(item, "type", None) == "image_generation_call":
            image_base64 = item.result
            break
    if not image_base64:
        return None, "이미지 결과를 찾지 못했습니다."

    image_path = Path(tempfile.mkdtemp(prefix="blog-agent-image-")) / "cover.png"
    image_path.write_bytes(base64.b64decode(image_base64))
    return str(image_path), "이미지를 생성했습니다."


with gr.Blocks(title="Blog Agent Console") as demo:
    gr.Markdown(
        """
        # Blog Agent Console

        GitHub Pages + WordPress 자동 블로그 운영 전, 초안과 대표 이미지를 확인하는 작업대입니다.
        """
    )

    with gr.Tab("Drafts"):
        with gr.Row():
            count = gr.Slider(1, 5, value=1, step=1, label="생성할 글 수")
            min_quality = gr.Slider(50, 100, value=65, step=1, label="최소 품질 점수")
        draft_button = gr.Button("초안 생성", variant="primary")
        draft_summary = gr.Textbox(label="생성 결과", lines=12)
        draft_body = gr.Textbox(label="첫 번째 초안 Markdown", lines=20)
        draft_button.click(generate_drafts, [count, min_quality], [draft_summary, draft_body])

    with gr.Tab("Image"):
        image_title = gr.Textbox(label="글 제목")
        image_body = gr.Textbox(label="본문/요약", lines=8)
        image_style = gr.Dropdown(
            ["clean editorial", "minimal infographic", "realistic lifestyle", "tech magazine", "public policy guide"],
            value="clean editorial",
            label="이미지 스타일",
        )
        prompt_button = gr.Button("이미지 프롬프트 만들기")
        image_prompt = gr.Textbox(label="Image Prompt", lines=8)
        image_button = gr.Button("대표 이미지 생성", variant="primary")
        image_output = gr.Image(label="Generated cover image", type="filepath")
        image_status = gr.Textbox(label="상태")
        prompt_button.click(build_image_prompt, [image_title, image_body, image_style], image_prompt)
        image_button.click(generate_image, image_prompt, [image_output, image_status])


if __name__ == "__main__":
    demo.launch()

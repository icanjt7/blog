from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


_REVIEW_DATA_PATH = Path(__file__).with_name("product_reviews.json")
try:
    PRODUCT_REVIEW_DATA: dict[str, dict] = json.loads(_REVIEW_DATA_PATH.read_text(encoding="utf-8"))
except (OSError, ValueError):
    PRODUCT_REVIEW_DATA = {}


@dataclass(frozen=True)
class ProductLink:
    name: str
    url: str
    keywords: tuple[str, ...]

    @property
    def image_url(self) -> str:
        return PRODUCT_IMAGE_URLS.get(self.url.rsplit("/", 1)[-1], "")

    @property
    def review_data(self) -> dict:
        return PRODUCT_REVIEW_DATA.get(self.url.rsplit("/", 1)[-1], {})


def product(name: str, code: str, *keywords: str) -> ProductLink:
    return ProductLink(name=name, url=f"https://toss.im/_m/{code}", keywords=keywords)


PRODUCT_LINKS: tuple[ProductLink, ...] = (
    product("더건강플러스 엑스트라버진 올리브오일 1L", "9FHICi7b", "올리브오일", "올리브유", "요리", "식품", "건강"),
    product("동아제약 얼박사 355ml 48개", "h5pr4yMt", "음료", "피로", "박카스", "비타민", "건강"),
    product("다원 통찜용 자연산 한치 500g", "5wFfPBws", "한치", "오징어", "해산물", "수산물", "요리", "식품"),
    product("국내산 한돈 1+등급 돼지 뒷고기 구이용 4팩", "3PQAFahr", "한돈", "돼지고기", "고기", "구이", "식품"),
    product("해선푸드 명태포 슬라이스 700g", "xJVyKiMo", "명태", "명태포", "생선", "해산물", "수산물", "식품"),
    product("국내산 햇 양파 3kg", "rVrJRN2l", "양파", "채소", "농산물", "요리", "식품"),
    product("명태포 슬라이스 700g 2팩", "Nia49byd", "명태", "명태포", "생선", "해산물", "수산물", "식품"),
    product("블로즈 리페어 재생크림 70ml 2개", "N3xbHSN9", "재생크림", "크림", "피부", "스킨케어", "화장품", "뷰티"),
    product("생 칵테일 새우 대 900g", "b8k0T0j7", "새우", "해산물", "수산물", "요리", "식품"),
    product("블로즈 리페어 재생크림 70ml 3개", "rtWorPL5", "재생크림", "크림", "피부", "스킨케어", "화장품", "뷰티"),
    product("건어물명가 반건조 노가리 500g", "1udvQHy3", "노가리", "건어물", "생선", "안주", "해산물", "식품"),
    product("다원 통찜용 자연산 한치 500g 2개", "vvZhux31", "한치", "오징어", "해산물", "수산물", "요리", "식품"),
    product("한미양행 보스웰리아 콘드로이친 플러스 세트", "ZMbzByhw", "보스웰리아", "콘드로이친", "관절", "연골", "영양제", "건강"),
    product("한미양행 혈당 혈압 혈행 트리플케어", "FleCbTLt", "혈당", "혈압", "혈행", "영양제", "건강"),
    product("아토몽드 더마 헤어젤 160g", "hpXSfo2q", "헤어젤", "헤어", "머리", "스타일링", "뷰티"),
    product("머스크 메론 선물세트 4kg", "TeiSmw0c", "메론", "멜론", "과일", "선물", "농산물", "식품"),
    product("운동화 세탁망 40x20cm 2개", "jx7ztL1g", "운동화", "세탁", "세탁망", "신발", "청소", "생활"),
    product("헤어유레카 CLPP 단백질 트리트먼트 1L", "lkl160ih", "트리트먼트", "단백질", "모발", "헤어", "뷰티"),
    product("미르바네스 여성 데일리 핀턱 밴딩 슬랙스", "ZBKfVyKk", "여성", "슬랙스", "바지", "패션", "의류", "생활"),
    product("블로즈 엑소셀 마스크팩 5매", "PjgLybem", "마스크팩", "팩", "피부", "스킨케어", "화장품", "뷰티"),
    product("에어보나 올클린 스팀 클렌저 AB-SM800", "7vyrQSwn", "스팀", "클렌저", "청소기", "청소", "가전", "기술", "생활"),
    product("삼형제 쪽파 파김치 2kg", "NSfk8Vdr", "파김치", "김치", "반찬", "식품", "요리"),
    product("종근당건강 프로메가 알티지 오메가3 듀얼S", "lnQdq7ws", "오메가3", "혈행", "면역", "비타민", "영양제", "건강"),
    product("피죤 스프레이 섬유탈취제 3종", "HHjMy3Mt", "탈취제", "섬유", "세탁", "향기", "청소", "생활"),
    product("비엣꿀 베트남 천연벌꿀 아카시아꿀 2kg", "FFWBSJ0A", "벌꿀", "꿀", "아카시아", "건강", "식품"),
    product("바이오던스 콜라겐 아이패치 60입", "lyW3jeZA", "콜라겐", "아이패치", "눈가", "피부", "스킨케어", "뷰티"),
    product("밀크아트 플레인 요구르트 무가당 1L 2개", "b5hTcCvC", "요구르트", "요거트", "유산균", "우유", "건강", "식품"),
    product("윙잇 정통 인계동 해장국 600g 3개", "xKBhEny3", "해장국", "국", "간편식", "식품", "요리"),
    product("맘스터치 시그니처 치킨텐더 1kg 2개", "RQeQWW26", "치킨", "닭고기", "텐더", "간편식", "식품"),
    product("BNR17 다이어트유산균 비에날씬 3박스", "t2L5eTh7", "다이어트", "유산균", "장건강", "영양제", "건강"),
    product("랜선식당 프리미엄 양념 LA갈비 400g", "5ebEYiud", "갈비", "소고기", "고기", "구이", "식품"),
    product("수입 대패삼겹 1kg 2팩", "js5A5KJe", "대패삼겹", "삼겹살", "돼지고기", "고기", "식품"),
    product("오에스알 미드나잇 EGF 리페어 크림 70ml", "9BtmmW1g", "EGF", "리페어", "크림", "피부", "스킨케어", "뷰티"),
    product("맥클린 시크릿 멀티밤 10g 2개", "Jfi7lCeh", "멀티밤", "보습", "피부", "스킨케어", "뷰티"),
    product("욱진담 한우 모듬구이 1++ 400g 2개", "97WU1Sfi", "한우", "소고기", "모듬구이", "고기", "식품"),
    product("비비고 왕교자 1.05kg 3개", "Ne3H0KKk", "만두", "왕교자", "간편식", "식품", "요리"),
    product("육진담 한우 모듬구이 1++ 400g 3개", "PJwME6er", "한우", "소고기", "모듬구이", "고기", "식품"),
    product("횡성축협한우 국내산 소불고기 1등급 200g", "Vo3tJxts", "한우", "소불고기", "불고기", "소고기", "고기", "식품"),
    product("횡성축협한우 국내산 국거리 1등급 200g 2개", "f3qbFxMt", "한우", "국거리", "소고기", "고기", "국", "식품"),
    product("육진담 한우 1++ 혼합 모듬구이 600g", "XmJU4qYu", "한우", "소고기", "모듬구이", "고기", "식품"),
    product("호주산 블랙앵거스 양념 LA갈비 500g 8개", "p7hHp7hw", "LA갈비", "갈비", "소고기", "고기", "식품"),
    product("노랑 곱빼기 왕 떡갈비 160g 5봉", "VyS3wxuy", "떡갈비", "갈비", "고기", "간편식", "식품"),
    product("탐나유 캠벨포도 2kg", "Xw7cyJLD", "포도", "과일", "농산물", "식품"),
)


PRODUCT_IMAGE_URLS: dict[str, str] = {
    "9FHICi7b": "https://shopping.toss.im/live/temp/2026-06-05/28f63f1a-246e-4e36-82ad-12f0fbb50755.jpeg",
    "h5pr4yMt": "https://shopping.toss.im/live/temp/2026-03-17/c9028546-ba19-4014-8c8b-c85d37eda844.jpeg",
    "5wFfPBws": "https://shopping.toss.im/live/taca/ai/MzI0ZDg5/TThBR1RoMlZHeVluYWN4R09jOHpCdWM4L3VBZ253QXlIV1ovL2hIKzhERT0.png",
    "3PQAFahr": "https://shopping.toss.im/live/temp/2026-09-05/79a1ea10-1db9-4b33-8d21-f63edae43be4.png",
    "xJVyKiMo": "https://shopping.toss.im/live/product/38416887/079a5cc4-cb45-486d-88a6-80c95f274ad4.jpeg",
    "rVrJRN2l": "https://shopping.toss.im/live/taca/ai/N2QxNTY5/SUc1RTRlZVV5ZGZxMisxajI3L2E5SFMyV2t1UW04dytUOVFLL09mUUlNQT0.png",
    "Nia49byd": "https://shopping.toss.im/bcfc2811-ee2b-42b3-bde7-06d7498e4bb4.jpg",
    "N3xbHSN9": "https://shopping.toss.im/live/temp/2026-07-07/9d81186a-4a50-4721-8e2a-4d8c762a9b33.png",
    "b8k0T0j7": "https://shopping.toss.im/live/taca/ai/MzFjMjQw/R2xGWkIzUHR0dUdVajZjeExtZzhUTGpLNGJObkpGMFozRE5DQS9mK2Zrdz0.png",
    "rtWorPL5": "https://shopping.toss.im/live/temp/2026-07-07/9d81186a-4a50-4721-8e2a-4d8c762a9b33.png",
    "1udvQHy3": "https://shopping.toss.im/live/temp/2026-06-04/8e1e7348-8121-4641-a08a-c44cc17fb846.jpeg",
    "vvZhux31": "https://shopping.toss.im/live/taca/ai/MzI0ZDg5/TThBR1RoMlZHeVluYWN4R09jOHpCdWM4L3VBZ253QXlIV1ovL2hIKzhERT0.png",
    "ZMbzByhw": "https://shopping.toss.im/live/taca/ai/v2/ZTEzNGRl/SzNhemRrczIrM1JFMzNiRVptUnVWdXRjcVVhNW5OdE91WnhLYTFhWmxMaz0.png",
    "FleCbTLt": "https://shopping.toss.im/live/temp/2026-09-08/01499a77-372a-48b9-81b4-56d7aa33fcb5.jpeg",
    "hpXSfo2q": "https://shopping.toss.im/live/taca/ai/v2/NmY1MTIy/RGJHU1p2L09OdFBDZm0wc21iSGpiRzNCdHBPU0hva3haL2hKYUxBQnR0WT0.png",
    "TeiSmw0c": "https://shopping.toss.im/live/temp/2026-08-28/4368f403-3673-4fe9-aa1c-6e74293ae2df.jpeg",
    "jx7ztL1g": "https://shopping.toss.im/live/temp/2025-08-05/0c32948a-5e0e-4d82-8e56-2a74ee2d3196.jpeg",
    "lkl160ih": "https://shopping.toss.im/live/temp/2025-12-16/1aad062f-3026-4675-9b87-15aa042d873f.jpeg",
    "ZBKfVyKk": "https://shopping.toss.im/live/temp/2026-04-06/16393d57-2a1d-401b-b19e-7563d3c2640c.jpeg",
    "PjgLybem": "https://shopping.toss.im/live/temp/2026-06-17/3e1cddbc-6714-42f9-9fbe-fe7f9a27698c.png",
    "7vyrQSwn": "https://shopping.toss.im/live/temp/2025-05-29/c44ac161-ec23-4a1e-8bd7-2ca71d3bf466.jpeg",
    "NSfk8Vdr": "https://shopping.toss.im/live/taca/ai/NzMyZDQw/QVBPZi9qZFR6TjV1eHMxWnpUOFpNem44T2MyWjBmRHpkZ3YwcmJ1OVE5Wms.png",
    "lnQdq7ws": "https://shopping.toss.im/live/temp/2026-07-23/1ca91ba3-3fbc-4d2a-a465-97195ba48b2a.jpeg",
    "HHjMy3Mt": "https://shopping.toss.im/live/temp/2026-09-18/e0139823-e091-409b-8d2c-6ca119b80bca.jpeg",
    "FFWBSJ0A": "https://shopping.toss.im/live/taca/ai/MDY3Zjli/YUU3WGMxaXN4bE5ydFk1eThCNlpaViswZXMwUUo5cUV0dnlHbG9BQmJGST0.png",
    "lyW3jeZA": "https://shopping.toss.im/live/taca/ai/v2/NTM0NzEw/T1pTTmllTWJqR1NtV3hua3hwdGpqQTQySm14NDVzZVlpWnNjT2FWTFlzWT0.png",
    "b5hTcCvC": "https://shopping.toss.im/live/taca/ai/ZmJhZjEw/SkpMSE04TTVjSXd5ekJqbUhUTENjZWNMWll4QzdKQlduYkNnNldaUEtXMD0.png",
    "xKBhEny3": "https://shopping.toss.im/live/taca/ai/ODJjMjdi/Zjk4T0RXMiszRHdaaDVqalRKUXVML3Mybk9iK08zNDI0em5nSCtBU2dOZz0.png",
    "RQeQWW26": "https://shopping.toss.im/live/taca/ai/ODdlMGY5/WnR6a3k4emJsWnJwa3pNZWJiT21NZWptS0dXa3pxR1RrUnpUWTNSWVljST0.png",
    "t2L5eTh7": "https://shopping.toss.im/live/temp/2026-09-14/37b2d5a3-e1c7-49a2-895b-6fcd9ce94a07.jpeg",
    "5ebEYiud": "https://shopping.toss.im/live/temp/2025-01-23/a5cec8b0-4ee3-4f3f-ba7e-f6234490df1f.jpeg",
    "js5A5KJe": "https://shopping.toss.im/live/temp/2026-08-04/900dfa86-ac6c-46b5-87fd-c1ad501781e8.jpeg",
    "9BtmmW1g": "https://shopping.toss.im/live/taca/ai/NWY2ZGFl/ZEFzSjZBbFU5QjRWL2dBRDZBRW8zQVZVVkN0YXF5Z0JvVUZVL2gvK0lBRT0.png",
    "Jfi7lCeh": "https://shopping.toss.im/live/taca/ai/OWJjNGYw/QUxIM1NoNU9mS2VmYzQ1NVFiM0RyYWVZZUs0TlRnTkhZSkx6cHJ4cEIybHY.png",
    "97WU1Sfi": "https://shopping.toss.im/10c/live/product/768502791/10cfc1c2-af54-4ae6-8c7b-18b341703311.jpg",
    "Ne3H0KKk": "https://shopping.toss.im/live/taca/ai/YTIwNTAw/QUpETGFieVdlbnA4UE02aHNzOW9ucGw1RWVRTFV6Tmt3L09GL2lNOGVSSDg.png",
    "PJwME6er": "https://shopping.toss.im/10c/live/product/768502791/10cfc1c2-af54-4ae6-8c7b-18b341703311.jpg",
    "Vo3tJxts": "https://shopping.toss.im/d9a/live/product/757752015/d9ad127b-36d9-4528-895c-15479b6ac0ce.jpg",
    "f3qbFxMt": "https://shopping.toss.im/f0f/live/product/757486213/f0f5d4f7-23ee-45a3-8131-a005f27e40d5.jpg",
    "XmJU4qYu": "https://shopping.toss.im/live/taca/ai/v2/NWI5ODQ4/QUx3OEppN0d3ODRabUNRdkhtVGg4K0ErR21qaWltRXFPYVh0NjhWVDlKZ2Y.png",
    "p7hHp7hw": "https://shopping.toss.im/b39/live/product/840696581/b394d955-7779-40ba-b12c-b7bf184fa00c.jpg",
    "VyS3wxuy": "https://shopping.toss.im/955d5c28-ce13-4baa-9f0a-f06de476fcc0.jpg",
    "Xw7cyJLD": "https://shopping.toss.im/live/taca/ai/v2/MWJkZjAx/QUl1SkozcmRlMmtJMUEwMUtRcWxHUWptOVZ5dnZSV3VyVnhVSHJSUkR1Lys.png",
}

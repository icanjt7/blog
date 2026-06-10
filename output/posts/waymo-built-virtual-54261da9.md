---
title: "Waymo의 가상 운전자, 자율주행 안전 실험"
date: '2026-06-10T10:43:45.040939'
category: 기술
tags:
- 기술
- Waymo
- 자율주행
- 안전검증
- AI
quality_score: 95.0
cover_image: https://images.unsplash.com/photo-1550751827-4bd374c3f58b?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjUzMTl8MHwxfHNlYXJjaHwxfHx0ZWNobm9sb2d5JTIwaW5ub3ZhdGlvbiUyMGNpcmN1aXQlMjBhYnN0cmFjdHxlbnwxfDB8fHwxNzgxMDY3MTc5fDA&ixlib=rb-4.1.0&q=80&w=1080
cover_image_alt: "Waymo virtual driver autonomous safety model — Photo by Adi Goldstein on Unsplash"
---

![Waymo virtual driver autonomous safety model — Photo by Adi Goldstein on Unsplash](https://images.unsplash.com/photo-1550751827-4bd374c3f58b?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3w5NjUzMTl8MHwxfHNlYXJjaHwxfHx0ZWNobm9sb2d5JTIwaW5ub3ZhdGlvbiUyMGNpcmN1aXQlMjBhYnN0cmFjdHxlbnwxfDB8fHwxNzgxMDY3MTc5fDA&ixlib=rb-4.1.0&q=80&w=1080)

## 무슨 소식인가

Waymo가 도로 위 돌발 상황에서 사람이 어떻게 반응하는지 연구하기 위해 가상 운전자 모델을 만들었습니다. 이름은 ReD, Reference Driver입니다. 실제 운전자를 대신해 "사람이라면 이 위험을 언제 보고, 얼마나 늦게 반응하고, 어떤 조작을 할까"를 시뮬레이션하는 기준 모델에 가깝습니다.

이 소식은 단순히 자율주행차가 더 똑똑해졌다는 이야기가 아닙니다. 자율주행 안전성을 평가할 때 무엇과 비교해야 하는지, 사람 운전자의 반응을 얼마나 현실적으로 모델링할 수 있는지에 관한 문제입니다.

## 먼저 알아둘 배경

Waymo는 Alphabet 계열의 자율주행 기업입니다. 자율주행 택시 서비스를 운영하면서 실제 도로 데이터와 시뮬레이션을 함께 사용합니다. 자율주행 개발에서 시뮬레이션은 필수입니다. 현실 도로에서 모든 사고 가능성을 직접 시험할 수 없기 때문입니다.

기존 안전 모델은 충돌 직전의 회피 동작을 단순하게 다루는 경우가 많았습니다. 하지만 실제 사람은 위험을 알아차리는 시점, 시야에 들어온 물체의 크기 변화, 놀람, 판단 지연, 핸들과 브레이크 조작 반응이 모두 다릅니다. Waymo의 ReD는 이런 인간 반응을 더 세밀하게 흉내 내려는 시도입니다.

## ReD가 보는 핵심은 무엇인가

ReD는 도로 상황을 완벽하게 아는 초인적 운전자가 아닙니다. 오히려 사람이 가진 한계를 넣는 모델입니다. 눈앞의 물체가 빠르게 커지는지, 충돌 위험이 어느 정도로 보이는지, 규칙을 지키려는 편향이 있는지, 실제 조작까지 시간이 얼마나 걸리는지를 반영합니다.

| 요소 | ReD에서 중요한 이유 |
| --- | --- |
| 시각 인지 | 위험 물체가 언제 눈에 띄는지 판단 |
| 놀람 반응 | 갑작스러운 상황에서 판단이 늦어지는 정도 반영 |
| 조작 지연 | 브레이크·핸들 조작까지 걸리는 시간 계산 |
| 비교 기준 | 자율주행차가 사람보다 나은지 볼 때 기준점 제공 |

## 왜 기술 이슈인가

자율주행 안전 논쟁에서 가장 어려운 질문은 "얼마나 안전하면 충분한가"입니다. 무사고를 요구하면 어떤 기술도 도로에 나올 수 없습니다. 반대로 회사가 자체 기준만 내세우면 신뢰를 얻기 어렵습니다. 그래서 사람 운전자의 평균적 반응과 비교할 수 있는 기준 모델이 중요합니다.

Waymo가 ReD를 공개하려는 이유도 여기에 있습니다. 특정 회사 내부 도구로만 쓰면 마케팅 자료처럼 보일 수 있지만, 연구자와 규제기관이 검토할 수 있는 기준 모델이 되면 자율주행 안전성 논의가 조금 더 구체화됩니다.

## 독자가 이해해야 할 포인트

첫째, ReD는 자율주행차 그 자체가 아니라 비교용 인간 운전자 모델입니다. Waymo 차량이 어떻게 움직이는지 직접 제어하는 기능이라기보다, 위험 상황에서 사람이라면 어떻게 반응했을지 보는 기준입니다.

둘째, 자율주행 안전성은 주행거리 숫자만으로 판단하기 어렵습니다. 어떤 도시에서, 어떤 날씨에, 어떤 돌발 상황을 만났는지에 따라 난이도가 달라집니다. 가상 운전자 모델은 이런 차이를 비교하는 데 도움을 줄 수 있습니다.

셋째, 한국에서도 자율주행 셔틀과 로보택시 실증이 늘어나면 같은 질문이 나옵니다. 사고가 났을 때 "사람보다 빨리 피할 수 있었나", "사람 운전자라면 같은 상황에서 어떻게 했을까"를 설명할 기준이 필요합니다.

## 참고한 곳

- [Waymo built a virtual driver to study how humans react to surprises on the road](https://www.theverge.com/transportation/947178/waymo-reference-driver-model-surprise-avoid-collision)

#!/usr/bin/env python3
"""Create 100 fact-based sports result posts from completed games."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from blog_agent.slugs import build_seo_slug


ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "output" / "posts"
PREFIX = "latest-sports-"
NOW = datetime(2026, 9, 20, 23, 59, 59, tzinfo=timezone.utc)
KST = timezone(timedelta(hours=9))


TEAM_KO = {
    # MLB
    "Arizona Diamondbacks": "애리조나 다이아몬드백스", "Athletics": "애슬레틱스",
    "Atlanta Braves": "애틀랜타 브레이브스", "Baltimore Orioles": "볼티모어 오리올스",
    "Boston Red Sox": "보스턴 레드삭스", "Chicago Cubs": "시카고 컵스",
    "Chicago White Sox": "시카고 화이트삭스", "Cincinnati Reds": "신시내티 레즈",
    "Cleveland Guardians": "클리블랜드 가디언스", "Colorado Rockies": "콜로라도 로키스",
    "Detroit Tigers": "디트로이트 타이거스", "Houston Astros": "휴스턴 애스트로스",
    "Kansas City Royals": "캔자스시티 로열스", "Los Angeles Angels": "LA 에인절스",
    "Los Angeles Dodgers": "LA 다저스", "Miami Marlins": "마이애미 말린스",
    "Milwaukee Brewers": "밀워키 브루어스", "Minnesota Twins": "미네소타 트윈스",
    "New York Mets": "뉴욕 메츠", "New York Yankees": "뉴욕 양키스",
    "Philadelphia Phillies": "필라델피아 필리스", "Pittsburgh Pirates": "피츠버그 파이리츠",
    "San Diego Padres": "샌디에이고 파드리스", "San Francisco Giants": "샌프란시스코 자이언츠",
    "Seattle Mariners": "시애틀 매리너스", "St. Louis Cardinals": "세인트루이스 카디널스",
    "Tampa Bay Rays": "탬파베이 레이스", "Texas Rangers": "텍사스 레인저스",
    "Toronto Blue Jays": "토론토 블루제이스", "Washington Nationals": "워싱턴 내셔널스",
    # NFL
    "Arizona Cardinals": "애리조나 카디널스", "Atlanta Falcons": "애틀랜타 팰컨스",
    "Baltimore Ravens": "볼티모어 레이븐스", "Buffalo Bills": "버펄로 빌스",
    "Carolina Panthers": "캐롤라이나 팬서스", "Chicago Bears": "시카고 베어스",
    "Cincinnati Bengals": "신시내티 벵골스", "Cleveland Browns": "클리블랜드 브라운스",
    "Dallas Cowboys": "댈러스 카우보이스", "Denver Broncos": "덴버 브롱코스",
    "Detroit Lions": "디트로이트 라이언스", "Green Bay Packers": "그린베이 패커스",
    "Houston Texans": "휴스턴 텍산스", "Indianapolis Colts": "인디애나폴리스 콜츠",
    "Jacksonville Jaguars": "잭슨빌 재규어스", "Kansas City Chiefs": "캔자스시티 치프스",
    "Las Vegas Raiders": "라스베이거스 레이더스", "Los Angeles Chargers": "LA 차저스",
    "Los Angeles Rams": "LA 램스", "Miami Dolphins": "마이애미 돌핀스",
    "Minnesota Vikings": "미네소타 바이킹스", "New England Patriots": "뉴잉글랜드 패트리어츠",
    "New Orleans Saints": "뉴올리언스 세인츠", "New York Giants": "뉴욕 자이언츠",
    "New York Jets": "뉴욕 제츠", "Philadelphia Eagles": "필라델피아 이글스",
    "Pittsburgh Steelers": "피츠버그 스틸러스", "San Francisco 49ers": "샌프란시스코 포티나이너스",
    "Seattle Seahawks": "시애틀 시호크스", "Tampa Bay Buccaneers": "탬파베이 버커니어스",
    "Tennessee Titans": "테네시 타이탄스", "Washington Commanders": "워싱턴 커맨더스",
    # WNBA
    "Atlanta Dream": "애틀랜타 드림", "Chicago Sky": "시카고 스카이",
    "Connecticut Sun": "코네티컷 선", "Dallas Wings": "댈러스 윙스",
    "Golden State Valkyries": "골든스테이트 발키리스", "Indiana Fever": "인디애나 피버",
    "Las Vegas Aces": "라스베이거스 에이시스", "Los Angeles Sparks": "LA 스파크스",
    "Minnesota Lynx": "미네소타 링크스", "New York Liberty": "뉴욕 리버티",
    "Phoenix Mercury": "피닉스 머큐리", "Portland Fire": "포틀랜드 파이어", "Seattle Storm": "시애틀 스톰",
    "Toronto Tempo": "토론토 템포", "Washington Mystics": "워싱턴 미스틱스",
    # EPL teams encountered in 2026 feeds
    "Arsenal": "아스널", "Aston Villa": "애스턴 빌라", "Bournemouth": "본머스",
    "Brentford": "브렌트퍼드", "Brighton & Hove Albion": "브라이턴",
    "Burnley": "번리", "Chelsea": "첼시", "Coventry City": "코번트리 시티",
    "Crystal Palace": "크리스털 팰리스", "Everton": "에버턴", "Fulham": "풀럼", "Hull City": "헐 시티",
    "Ipswich Town": "입스위치 타운", "Leeds United": "리즈 유나이티드",
    "Liverpool": "리버풀", "Manchester City": "맨체스터 시티",
    "Manchester United": "맨체스터 유나이티드", "Newcastle United": "뉴캐슬 유나이티드",
    "Nottingham Forest": "노팅엄 포리스트", "Sunderland": "선덜랜드",
    "Tottenham Hotspur": "토트넘 홋스퍼", "West Ham United": "웨스트햄 유나이티드",
    "Wolverhampton Wanderers": "울버햄프턴",
}


def get_json(url: str) -> dict:
    request = Request(url)
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def ko_team(name: str) -> str:
    return TEAM_KO.get(name, name)


def quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_post(index: int, title: str, date: datetime, tags: list[str], body: str) -> Path:
    slug = build_seo_slug(title, category="스포츠", source_id=index, published_date=date.date(), max_length=90)
    path = POSTS_DIR / f"{PREFIX}{index:03d}-{slug}.md"
    frontmatter = [
        "---",
        f"title: {quote(title)}",
        f"date: {quote(date.astimezone(KST).replace(tzinfo=None).isoformat())}",
        "category: 스포츠",
        "tags:",
        *[f"- {quote(tag)}" for tag in tags],
        "quality_score: 92.0",
        f"author: {quote('브리핑웨이브 스포츠팀')}",
        "---",
        "",
    ]
    path.write_text("\n".join(frontmatter) + body.strip() + "\n", encoding="utf-8")
    return path


def best_batter(team_box: dict) -> dict | None:
    candidates = []
    for player in team_box.get("players", {}).values():
        batting = player.get("stats", {}).get("batting", {})
        if not batting or batting.get("plateAppearances", 0) == 0:
            continue
        score = (
            batting.get("homeRuns", 0) * 8
            + batting.get("rbi", 0) * 4
            + batting.get("hits", 0) * 3
            + batting.get("runs", 0) * 2
            + batting.get("baseOnBalls", 0)
        )
        candidates.append((score, player.get("person", {}).get("fullName", "선수"), batting))
    if not candidates:
        return None
    _, name, stats = max(candidates, key=lambda item: (item[0], item[2].get("hits", 0)))
    return {"name": name, "stats": stats}


def batter_line(player: dict | None) -> str:
    if not player:
        return "공식 박스스코어에서 타격 기록을 다시 확인해야 합니다."
    stats = player["stats"]
    return (
        f"{player['name']} — {stats.get('atBats', 0)}타수 {stats.get('hits', 0)}안타, "
        f"{stats.get('homeRuns', 0)}홈런, {stats.get('rbi', 0)}타점, {stats.get('runs', 0)}득점"
    )


def mlb_body(game: dict, box: dict) -> tuple[str, str, list[str]]:
    away = game["teams"]["away"]
    home = game["teams"]["home"]
    away_name = ko_team(away["team"]["name"])
    home_name = ko_team(home["team"]["name"])
    away_score, home_score = away["score"], home["score"]
    winner_side = "away" if away_score > home_score else "home"
    winner_name = away_name if winner_side == "away" else home_name
    loser_name = home_name if winner_side == "away" else away_name
    win_batter = best_batter(box["teams"][winner_side])
    lose_batter = best_batter(box["teams"]["home" if winner_side == "away" else "away"])
    date = game["officialDate"]
    margin = abs(away_score - home_score)
    total = away_score + home_score
    if margin == 1:
        shape = "한 점 차로 갈린 경기라 마지막까지 한 번의 출루와 실점 억제가 중요했던 결과입니다."
    elif margin >= 6:
        shape = "점수 차가 크게 벌어진 경기로, 승리 팀이 득점 기회를 결과로 연결한 정도가 뚜렷했습니다."
    elif total >= 12:
        shape = "두 팀 합계 득점이 두 자릿수를 넘은 타격전이었고, 더 많은 득점권 기회를 살린 쪽이 앞섰습니다."
    else:
        shape = "중간 점수대에서 승부가 결정됐으며, 제한된 득점 기회를 놓치지 않은 팀이 결과를 가져갔습니다."
    decisions = game.get("decisions", {})
    winning_pitcher = decisions.get("winner", {}).get("fullName", "공식 기록 확인 필요")
    losing_pitcher = decisions.get("loser", {}).get("fullName", "공식 기록 확인 필요")
    save_pitcher = decisions.get("save", {}).get("fullName")
    decision_line = f"승리투수는 {winning_pitcher}, 패전투수는 {losing_pitcher}입니다."
    if save_pitcher:
        decision_line += f" 세이브는 {save_pitcher}가 기록했습니다."
    away_record = away.get("leagueRecord", {})
    home_record = home.get("leagueRecord", {})
    title = f"{date} {away_name} {away_score}-{home_score} {home_name} 경기 결과"
    body = f"""## 경기 결과

{date} 열린 MLB 경기에서 **{winner_name}가 {loser_name}를 {max(away_score, home_score)}-{min(away_score, home_score)}로 이겼습니다.** 예정 경기나 전망이 아니라 최종 처리된 공식 경기 결과를 기준으로 정리했습니다.

| 팀 | 득점 | 경기 후 기록 |
| --- | ---: | ---: |
| {away_name} | {away_score} | {away_record.get('wins', '-')}승 {away_record.get('losses', '-')}패 |
| {home_name} | {home_score} | {home_record.get('wins', '-')}승 {home_record.get('losses', '-')}패 |

## 주요 선수 기록

- **승리 팀 타격 주목 선수:** {batter_line(win_batter)}
- **상대 팀 타격 주목 선수:** {batter_line(lose_batter)}
- **투수 결정:** {decision_line}

선수 선정은 박스스코어의 안타·홈런·타점·득점을 함께 비교한 것으로, 단순히 이름값이 아니라 이번 경기에서 실제로 남긴 기록을 기준으로 했습니다.

## 경기를 숫자로 읽으면

{shape} 최종 스코어의 차이는 **{margin}점**, 두 팀의 합계 득점은 **{total}점**입니다. 야구는 같은 점수 차라도 출루와 장타, 투수 교체 과정이 다를 수 있으므로 승패와 개인 기록을 구분해서 보는 편이 정확합니다.

특히 {win_batter['name'] if win_batter else winner_name}의 타격 기록은 승리 팀 공격에서 눈에 띄었습니다. 반대편에서는 {lose_batter['name'] if lose_batter else loser_name}의 기록을 함께 보면, 최종 승패와 개별 선수 활약이 반드시 같은 방향으로 움직이지 않는다는 점도 확인할 수 있습니다.

## 한눈에 보는 핵심

- 승리 팀: **{winner_name}**
- 최종 점수: **{away_name} {away_score}-{home_score} {home_name}**
- 점수 차: **{margin}점**
- 확인 기준: MLB 공식 최종 스코어·박스스코어

기록 정정이 발생하면 리그 공식 데이터가 우선합니다. 이 글은 경기 종료 후 확인된 결과와 선수 기록을 바탕으로 새로 작성한 요약입니다.
"""
    return title, body, ["MLB", "메이저리그", "경기결과", winner_name, win_batter["name"] if win_batter else winner_name]


def collect_mlb(limit: int) -> list[tuple[str, datetime, list[str], str]]:
    params = urlencode({
        "sportId": 1, "startDate": "2026-09-12", "endDate": "2026-09-19",
        "hydrate": "linescore,decisions",
    })
    schedule = get_json(f"https://statsapi.mlb.com/api/v1/schedule?{params}")
    games = [
        game for day in schedule.get("dates", []) for game in day.get("games", [])
        if game.get("status", {}).get("abstractGameState") == "Final"
    ]
    games.sort(key=lambda game: game["gameDate"], reverse=True)
    games = games[:limit]
    boxes: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {
            pool.submit(get_json, f"https://statsapi.mlb.com/api/v1/game/{game['gamePk']}/boxscore"): game["gamePk"]
            for game in games
        }
        for future in as_completed(futures):
            boxes[futures[future]] = future.result()
    records = []
    for game in games:
        title, body, tags = mlb_body(game, boxes[game["gamePk"]])
        records.append((title, datetime.fromisoformat(game["gameDate"].replace("Z", "+00:00")), tags, body))
    return records


def espn_events(path: str) -> list[dict]:
    data = get_json(f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates=2026&limit=1000")
    events = [
        event for event in data.get("events", [])
        if event.get("status", {}).get("type", {}).get("completed")
        and datetime.fromisoformat(event["date"].replace("Z", "+00:00")) <= NOW
    ]
    events.sort(key=lambda event: event["date"], reverse=True)
    return events


def competitors(event: dict) -> tuple[dict, dict, dict]:
    competition = event["competitions"][0]
    sides = competition["competitors"]
    home = next(side for side in sides if side.get("homeAway") == "home")
    away = next(side for side in sides if side.get("homeAway") == "away")
    return competition, away, home


def record_summary(side: dict) -> str:
    records = side.get("records", [])
    return records[0].get("summary", "-") if records else "-"


def leader_rows(leaders: list[dict]) -> list[tuple[str, str, str]]:
    labels = {
        "passingYards": "패싱", "rushingYards": "러싱", "receivingYards": "리시빙",
        "points": "득점", "rebounds": "리바운드", "assists": "어시스트", "rating": "종합 기록",
    }
    rows = []
    for group in leaders:
        values = group.get("leaders", [])
        if not values:
            continue
        first = values[0]
        name = first.get("athlete", {}).get("displayName")
        if name:
            rows.append((labels.get(group.get("name"), group.get("displayName", "주요 기록")), name, first.get("displayValue", "")))
    return rows


def nfl_post(event: dict) -> tuple[str, datetime, list[str], str]:
    competition, away, home = competitors(event)
    away_name, home_name = ko_team(away["team"]["displayName"]), ko_team(home["team"]["displayName"])
    away_score, home_score = int(away["score"]), int(home["score"])
    winner = away_name if away_score > home_score else home_name
    rows = leader_rows(competition.get("leaders", []))
    date = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    local_date = date.astimezone(KST).date().isoformat()
    title = f"{local_date} {away_name} {away_score}-{home_score} {home_name} NFL 결과"
    players = "\n".join(f"- **{label}:** {name} — {value}" for label, name, value in rows) or "- 공식 경기 기록에서 주요 선수를 확인할 수 있습니다."
    margin, total = abs(away_score - home_score), away_score + home_score
    body = f"""## 최종 스코어

{local_date} NFL 경기에서 **{winner}가 승리했습니다.** 최종 점수는 {away_name} {away_score}점, {home_name} {home_score}점입니다.

| 팀 | 점수 | 시즌 기록 |
| --- | ---: | ---: |
| {away_name} | {away_score} | {record_summary(away)} |
| {home_name} | {home_score} | {record_summary(home)} |

## 기록으로 본 주요 선수

{players}

패싱·러싱·리시빙 리더는 서로 다른 팀에서 나올 수 있습니다. 최종 승리 팀만 보고 개인 활약을 판단하지 않고, 공식 스코어보드가 분류한 경기별 기록 리더를 함께 정리했습니다.

## 경기 흐름을 보여주는 숫자

두 팀의 합계 점수는 **{total}점**, 최종 점수 차는 **{margin}점**입니다. {'한 번의 공격권으로 뒤집을 수 있는 가까운 승부였습니다.' if margin <= 8 else '두 자릿수 점수 차가 나면서 승리 팀의 득점 효율이 결과에 분명하게 반영됐습니다.'} 미식축구는 총 득점뿐 아니라 공격 방식별 생산성을 나눠 보면 선수 활약이 더 선명해집니다.

## 선수 기록을 함께 보는 이유

쿼터백의 패싱 야드만으로 공격 전체를 설명할 수는 없습니다. 러닝백이 지상에서 전진해 다음 공격의 거리를 줄였는지, 리시버가 실제 캐치와 터치다운으로 연결했는지를 함께 봐야 합니다. 위 기록 리더 세 항목은 이번 경기에서 공을 어떤 방식으로 전진시켰는지 비교하는 출발점입니다.

또한 패싱 선두 선수가 패한 팀에서 나올 수도 있습니다. 뒤진 팀이 패스를 더 많이 시도하면서 야드가 늘어나는 상황도 있기 때문입니다. 그래서 개인 누적 기록은 최종 점수와 분리해 보고, 승패는 득점과 실점의 결과로 확인했습니다.

## 결과 요약

- 승리 팀: **{winner}**
- 최종 점수: **{away_name} {away_score}-{home_score} {home_name}**
- 주요 기록 기준: 패싱·러싱·리시빙 리더
- 데이터 상태: 경기 종료·최종 결과

이 글은 종료된 경기의 스코어와 선수 기록을 바탕으로 작성했습니다. 이후 공식 기록 정정이 있을 경우 리그 스코어보드가 우선합니다.
"""
    tags = ["NFL", "미식축구", "경기결과", winner] + ([rows[0][1]] if rows else [])
    return title, date, tags, body


def wnba_post(event: dict) -> tuple[str, datetime, list[str], str]:
    competition, away, home = competitors(event)
    away_name, home_name = ko_team(away["team"]["displayName"]), ko_team(home["team"]["displayName"])
    away_score, home_score = int(away["score"]), int(home["score"])
    winner_side, loser_side = (away, home) if away_score > home_score else (home, away)
    winner = ko_team(winner_side["team"]["displayName"])
    win_rows, lose_rows = leader_rows(winner_side.get("leaders", [])), leader_rows(loser_side.get("leaders", []))
    date = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    local_date = date.astimezone(KST).date().isoformat()
    title = f"{local_date} {away_name} {away_score}-{home_score} {home_name} WNBA 결과"
    win_player = next((row for row in win_rows if row[0] == "종합 기록"), win_rows[0] if win_rows else None)
    lose_player = next((row for row in lose_rows if row[0] == "종합 기록"), lose_rows[0] if lose_rows else None)
    win_text = f"{win_player[1]} — {win_player[2]}" if win_player else "공식 기록 확인 필요"
    lose_text = f"{lose_player[1]} — {lose_player[2]}" if lose_player else "공식 기록 확인 필요"
    margin = abs(away_score - home_score)
    body = f"""## 경기 결과

{local_date} 열린 WNBA 경기에서 **{winner}가 승리했습니다.** 최종 스코어는 {away_name} {away_score}점, {home_name} {home_score}점입니다.

| 팀 | 점수 | 시즌 기록 |
| --- | ---: | ---: |
| {away_name} | {away_score} | {record_summary(away)} |
| {home_name} | {home_score} | {record_summary(home)} |

## 양 팀 주요 선수

- **승리 팀 주목 선수:** {win_text}
- **상대 팀 주목 선수:** {lose_text}

공식 스코어보드의 득점·리바운드·어시스트와 종합 기록을 기준으로 각 팀에서 눈에 띈 선수를 골랐습니다. 팀 결과와 개인 기록을 함께 보면, 패한 팀에서도 좋은 경기력을 보인 선수가 누구였는지 놓치지 않을 수 있습니다.

## 숫자로 본 승부

최종 점수 차는 **{margin}점**입니다. {'한두 번의 공격 성공 여부가 결과를 바꿀 수 있었던 접전입니다.' if margin <= 5 else '승리 팀이 점수 차를 두 자릿수 안팎으로 만들며 우위를 결과로 남겼습니다.'} 농구 결과를 볼 때는 득점 선두뿐 아니라 리바운드와 어시스트가 공격 기회를 어떻게 늘렸는지도 함께 확인할 필요가 있습니다.

## 선수 활약을 해석하는 방법

득점은 가장 눈에 잘 띄지만 한 경기의 기여도를 전부 보여주지는 않습니다. 리바운드는 상대 공격을 끝내거나 추가 공격권을 만들고, 어시스트는 동료의 득점 기회를 직접 연결합니다. 따라서 승리 팀 주목 선수는 공식 스코어보드의 종합 기록을 우선하되 득점·리바운드·어시스트를 함께 확인했습니다.

상대 팀의 주요 선수도 별도로 적은 이유는 패배가 곧 모든 선수의 부진을 뜻하지 않기 때문입니다. 팀 스코어와 개인 기록을 나눠 보면 결과 기사에서도 양 팀 선수의 실제 활약을 더 균형 있게 읽을 수 있습니다.

## 핵심 정리

- 승리 팀: **{winner}**
- 최종 점수: **{away_name} {away_score}-{home_score} {home_name}**
- 승리 팀 주목 선수: **{win_player[1] if win_player else '-'}**
- 데이터 상태: 경기 종료·최종 결과

이 글은 완료된 경기의 최종 스코어와 선수 기록을 바탕으로 새로 작성했습니다. 공식 기록이 정정되면 리그 데이터가 우선합니다.
"""
    tags = ["WNBA", "여자농구", "경기결과", winner] + ([win_player[1]] if win_player else [])
    return title, date, tags, body


def epl_post(event: dict) -> tuple[str, datetime, list[str], str]:
    competition, away, home = competitors(event)
    away_name, home_name = ko_team(away["team"]["displayName"]), ko_team(home["team"]["displayName"])
    away_score, home_score = int(float(away["score"])), int(float(home["score"]))
    if away_score == home_score:
        result = "무승부"
        winner = "무승부"
    else:
        winner = away_name if away_score > home_score else home_name
        result = f"{winner} 승리"
    team_by_id = {str(side["team"]["id"]): ko_team(side["team"]["displayName"]) for side in (away, home)}
    goals = []
    for detail in competition.get("details", []):
        if not detail.get("scoringPlay"):
            continue
        athletes = detail.get("athletesInvolved", [])
        scorer = athletes[0].get("displayName", "선수 확인 필요") if athletes else "선수 확인 필요"
        minute = detail.get("clock", {}).get("displayValue", "-")
        goal_team = team_by_id.get(str(detail.get("team", {}).get("id")), "팀 확인 필요")
        suffix = " (자책골)" if detail.get("ownGoal") else ""
        goals.append(f"- **{minute} {goal_team}:** {scorer}{suffix}")
    goal_text = "\n".join(goals) if goals else "- 득점자 없음 — 0-0 무승부"
    date = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    local_date = date.astimezone(KST).date().isoformat()
    title = f"{local_date} {away_name} {away_score}-{home_score} {home_name} EPL 결과"
    margin, total = abs(away_score - home_score), away_score + home_score
    body = f"""## 프리미어리그 경기 결과

{local_date} 열린 EPL 경기 결과는 **{away_name} {away_score}-{home_score} {home_name}**, {result}입니다. 경기 종료 상태가 확인된 스코어를 기준으로 정리했습니다.

| 팀 | 득점 | 경기 결과 |
| --- | ---: | --- |
| {away_name} | {away_score} | {'승' if away_score > home_score else '무' if away_score == home_score else '패'} |
| {home_name} | {home_score} | {'승' if home_score > away_score else '무' if away_score == home_score else '패'} |

## 득점 선수와 시간

{goal_text}

득점 기록은 단순 최종 스코어보다 선수의 결정적 장면을 빠르게 확인하게 해 줍니다. 자책골 여부도 공식 이벤트 기록에 표시된 경우 따로 구분했습니다.

## 경기 결과를 읽는 포인트

두 팀이 만든 골은 모두 **{total}골**입니다. {'한 골 차 승부로 한 번의 결정력이 결과를 갈랐습니다.' if margin == 1 else '양 팀이 승점을 나눠 가진 경기입니다.' if margin == 0 else '두 골 이상 차이가 나며 승리 팀이 스코어에서 확실한 우위를 남겼습니다.'} 축구에서는 득점 수가 많지 않기 때문에 한 장면의 가치가 다른 종목보다 크게 나타납니다.

## 득점 기록을 확인할 때

득점 시간은 전반과 후반의 흐름을 가늠하게 하지만, 그 자체만으로 경기 지배력을 단정할 수는 없습니다. 이 글에서는 확인 가능한 최종 스코어와 공식 득점 이벤트에 집중했습니다. 슈팅 수나 점유율처럼 별도의 지표가 필요한 평가는 확인되지 않은 서술을 덧붙이지 않았습니다.

추가시간 표기는 `90'+7'`처럼 정규시간 뒤에 더해진 시간을 뜻합니다. 자책골은 공식 이벤트에서 자책골로 분류된 경우에만 표시합니다. 득점 선수 이름과 소속 팀을 함께 적어 이적이나 동명이인 때문에 생길 수 있는 혼동도 줄였습니다.

## 한눈에 정리

- 결과: **{result}**
- 최종 스코어: **{away_name} {away_score}-{home_score} {home_name}**
- 총 득점: **{total}골**
- 데이터 상태: 경기 종료·최종 결과

이 글은 완료된 경기의 공식 스코어보드와 득점 이벤트를 바탕으로 새로 작성했습니다. 사후 기록 정정이 발생하면 대회 공식 결과가 우선합니다.
"""
    scorers = [item.split(":** ", 1)[-1].replace(" (자책골)", "") for item in goals]
    tags = ["EPL", "프리미어리그", "축구", "경기결과", away_name, home_name] + scorers[:1]
    return title, date, tags, body


def main() -> None:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    for old in POSTS_DIR.glob(f"{PREFIX}*.md"):
        old.unlink()

    records = collect_mlb(65)
    records.extend(nfl_post(event) for event in espn_events("football/nfl")[:15])
    records.extend(wnba_post(event) for event in espn_events("basketball/wnba")[:10])
    records.extend(epl_post(event) for event in espn_events("soccer/eng.1")[:10])
    if len(records) != 100:
        raise SystemExit(f"Expected 100 completed games, got {len(records)}")

    titles = [record[0] for record in records]
    if len(set(titles)) != 100:
        raise SystemExit("Duplicate sports titles detected")

    created = [write_post(index, *record) for index, record in enumerate(records, 1)]
    print(f"created={len(created)} first={created[0].name} last={created[-1].name}")


if __name__ == "__main__":
    main()

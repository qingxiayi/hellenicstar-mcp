"""Finite source-paraphrase topics, not statements about a client's experience.

Chapter Two / The Descendant sign; Planets in the seventh house. Matching a
geometric condition selects a topic for observation, never proves projection.
"""
DESCENDANT_TOPICS = {
    'Ari': '伴侣期待中的行动、意志与愤怒表达',
    'Tau': '伴侣期待中的稳定、耐心与感官享受',
    'Gem': '伴侣期待中的轻松、提问与交流',
    'Can': '伴侣期待中的照料、情感联系与自身照料能力',
    'Leo': '伴侣期待中的喜悦、关注与独特感',
    'Vir': '伴侣期待中的辨别、审慎与界限',
    'Lib': '伴侣期待中的协调、平衡与顾及他人',
    'Sco': '伴侣期待中的深入、强烈情感与亲密联系',
    'Sag': '伴侣期待中的学习、文化差异与人生意义',
    'Cap': '伴侣期待中的结构、稳定与安全感',
    'Aqu': '伴侣期待中的空间、不同视角与客观观察',
    'Pis': '伴侣期待中的情感开放、照顾与创造性',
}
SEVENTH_TOPICS = {
    'sun': '关系中的自我认同与自我表达',
    'moon': '关系中的情感联系与情绪表达',
    'mercury': '关系中的沟通与表达所需',
    'venus': '关系中的价值感、欣赏与认可',
    'mars': '关系中的主动性、意愿与自我主张',
    'jupiter': '关系中的意义、成长与学习',
    'saturn': '关系中的责任、成熟与投入节奏',
    'uranus': '关系中的自由、独特性与关系形式',
    'neptune': '关系中的理想化、照顾与现实辨认',
    'pluto': '关系中的深入、变化与强烈情感',
    'chiron': '关系中的脆弱感与投入顾虑',
}


def projection_topics(profile):
    """Return only matched natal conditions; keep geometric evidence explicit."""
    points = profile['points']
    sign = points['descendant']['sign']
    yield dict(key='descendant_' + sign.lower(), topic=DESCENDANT_TOPICS[sign],
               source='descendant_topics', points=['descendant'],
               condition='descendant_sign_' + sign, evidence_points=['descendant'], aspect_indices=[])
    seventh = [p for p in SEVENTH_TOPICS if points[p]['effective_seventh_house']]
    for p in seventh:
        yield dict(key='seventh_' + p, topic=SEVENTH_TOPICS[p],
                   source='seventh_topics', points=[p],
                   condition='effective_seventh_house_planet', evidence_points=[p], aspect_indices=[])
    if {'venus', 'mars'} <= set(seventh):
        edges = [i for i, e in enumerate(profile['natal_aspects'])
                 if {e['first_point'], e['second_point']} == {'venus', 'mars'} and e['angle'] == 0]
        if edges:
            yield dict(key='seventh_venus_mars', topic='关系中的价值认可、自我主张及两者配合',
                       source='seventh_venus_mars', points=['venus', 'mars'],
                       condition='both_effective_seventh_and_natal_conjunction',
                       evidence_points=['venus', 'mars'], aspect_indices=edges)

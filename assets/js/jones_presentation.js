const jonesGeometry = require('./jones-geometry.js');

const PLANET_SYM = {
  太阳: '☉', 月亮: '☽', 水星: '☿', 金星: '♀', 火星: '♂',
  木星: '♃', 土星: '♄', 天王星: '♅', 海王星: '♆', 冥王星: '♇',
};

const ROLE_PRIORITY = {
  cog_bowl: 0, leader_loco: 0, handle: 0, handle1: 0, handle2: 0,
  handle_left: 0, handle_right: 0, isolated_butterfly: 0, isolated_splay: 0,
  isolated_tripod: 0,
  isolated_splash: 0, sellar_hfp: 0, sellar_hfp_trine: 0,
  cog_bowl_point: 0, void_bowl: 0,
  leader_bowl: 1, tail_bowl: 1, tail_loco: 1,
  boundary_bundle_left: 1, boundary_bundle_right: 1,
  bowl_edge_left: 1, bowl_edge_right: 1,
  bowl_edge_leading: 1, bowl_edge_trailing: 1,
  seesaw_pole_a: 1, seesaw_pole_b: 1,
};

function rolePriority(roleType) {
  const value = ROLE_PRIORITY[roleType];
  return value == null ? 1 : value;
}

const AXIS_NAMES = {
  ascendant: '上升点', descendant: '下降点', midheaven: '中天', imum_coeli: '天底',
};
const OUTER_PLANETS = ['天王星', '海王星', '冥王星'];

// 碗中心复合合相：承重墙卡片同时显示合相伙伴。
// 天王星、海王星、冥王星是世代行星：任何关键位置出现它们，都补一句“同一时期出生者共有”，
// 避免把世代共有的配置读成个人特征（Jones《Guide》文化线一章；Greene《命运占星》）。
// 注意公开文案禁词（备案要求）：你/性格/人格/命运/人生/使命/职业/心理/能量。
function generationNote(names) {
  const outer = names.filter(name => OUTER_PLANETS.includes(name));
  if (!outer.length) return '';
  if (names.length > 1 && outer.length === names.length) {
    return '这组外行星合相多为同一时期出生者共有，个别差异主要看所在宫位以及与对面把手的关系。';
  }
  return `${outer.join('、')}运行很慢，所在星座多为同一时期出生者共有，个别差异主要看所在宫位以及与其他行星的关系。`;
}

function withPartners(role) {
  const partners = Array.isArray(role.partners) ? role.partners.filter(p => p && p.planet_name) : [];
  const names = [role.planet_name].concat(partners.map(p => p.planet_name));
  const note = generationNote(names);
  const description = note ? `${role.description}${note}` : role.description;
  if (!partners.length) {
    return { displayName: role.planet_name, glyph: PLANET_SYM[role.planet_name] || '·', description };
  }
  return {
    displayName: names.join('＋'),
    glyph: names.map(name => PLANET_SYM[name] || '·').join(''),
    partnerNames: partners.map(p => p.planet_name),
    description,
  };
}
const ELEMENT_NAMES = ['火象', '土象', '风象', '水象'];
const MODALITY_NAMES = ['基本星座', '固定星座', '变动星座'];

function buildStateCopy(raw) {
  if (!raw) return '';
  if (
    raw.state === 'borderline'
    && raw.pattern_en === 'Bowl'
    && (raw.borderline_reasons || []).includes('碗型跨度上限交界')
  ) {
    return '这张盘的占据跨度接近或超出经典碗型的理想范围，但行星仍连成一条弧、没有断成两群，因此主标签保留为「碗型」。要观察的是碗内那段最宽的空白：它继续拉开到成群分隔的程度，这张盘就会转读成下面这一类。';
  }
  const copies = {
    standard: `行星分布清楚符合「${raw.pattern_zh}」的典型几何特征，当前计算结果明确。`,
    variant: `这张盘仍属于「${raw.family_zh}」家族，但整体分布呈现「${raw.pattern_zh}」变形。它不表示计算不确定。`,
    borderline: `这张盘位于几何交界。当前更接近「${raw.pattern_zh}」，少数行星只差几度可能改变分类。`,
  };
  return copies[raw.state] || '';
}

// 交界推荐：把后端算出的「另一种读法 + 距阈值度数差」压成一行短句。
// 界面上只占一行，与「交界原因」同级；不写解读结论，只给可对照的另一类次序。
function buildBorderlineHint(raw) {
  if (!raw || raw.state !== 'borderline') return null;
  const seen = new Set();
  const rows = [];
  (raw.borderline_alternates || []).forEach((alt) => {
    const pattern = alt && alt.pattern_zh;
    if (!pattern || pattern === raw.pattern_zh || seen.has(pattern)) return;
    seen.add(pattern);
    // Number(null) === 0：不先判空会把「后端没给度数差」渲染成「差 0.0°」，
    // 读起来像正好压在阈值上，与实际含义相反。
    const rawDelta = alt.delta_deg;
    const delta = (rawDelta === null || rawDelta === undefined || rawDelta === '')
      ? NaN : Number(rawDelta);
    rows.push({
      pattern,
      // 度数差要带上它量的是什么，否则界面上只有一个孤零零的数字，
      // 读盘的人没法对照分布环复核。
      delta: Number.isFinite(delta)
        ? `${alt.measure_zh ? alt.measure_zh + ' ' : ''}差 ${delta.toFixed(1)}°`
        : '',
    });
  });
  if (!rows.length) return null;
  return { label: '另一种读法', rows };
}

function uniqueValues(values) {
  return values.filter((value, index) => value && values.indexOf(value) === index);
}

function chartRulerText(context) {
  const asc = context && context.ascLongitude;
  if (typeof asc === 'number' && Number.isFinite(asc)) {
    const rulers = ['火星', '金星', '水星', '月亮', '太阳', '水星',
      '金星', '火星／冥王星', '木星', '土星', '土星／天王星', '木星／海王星'];
    return rulers[Math.floor(jonesGeometry.normalizedLongitude(asc) / 30)];
  }
  const chains = context && context.rulerChains;
  const rows = (chains && (chains.placidus || chains.whole_sign)) || [];
  const firstHouse = rows.find((row) => Number(row.house) === 1);
  const chainRulers = uniqueValues(((firstHouse && firstHouse.tracks) || [])
    .map((track) => track.house_ruler_zh));
  if (chainRulers.length) return chainRulers.join('／');
  // asc_ruler is a triplicity ruler in the API, not the Ascendant's domicile ruler.
  return '数据不足，请重新计算';
}

function angularPlanetText(raw, aspects) {
  if (!Array.isArray(aspects)) return '数据不足，请重新计算';
  const planetNames = new Set((raw.distribution || []).map((item) => item.name));
  const rows = (aspects || []).filter((aspect) => {
    const p1Axis = AXIS_NAMES[aspect.point1];
    const p2Axis = AXIS_NAMES[aspect.point2];
    const planet = p1Axis ? aspect.point2_zh : (p2Axis ? aspect.point1_zh : '');
    return aspect.aspect === '合相' && planetNames.has(planet)
      && typeof aspect.orb === 'number' && Number.isFinite(aspect.orb)
      && aspect.orb >= 0 && aspect.orb <= 3;
  }).map((aspect) => {
    const p1Axis = AXIS_NAMES[aspect.point1];
    const axis = p1Axis || AXIS_NAMES[aspect.point2];
    const planet = p1Axis ? aspect.point2_zh : aspect.point1_zh;
    return { planet, axis, orb: Number(aspect.orb) };
  }).sort((a, b) => a.orb - b.orb);
  const seen = new Set();
  const labels = rows.filter((row) => {
    const key = `${row.planet}-${row.axis}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).map((row) => {
    const orb = Number.isFinite(row.orb) ? `，距${row.orb.toFixed(1)}°` : '';
    return `${row.planet}（合${row.axis}${orb}）`;
  });
  return labels.length ? labels.join('；') : '未发现';
}

function singletonText(raw) {
  const distribution = raw.distribution || [];
  if (distribution.length !== 10 || new Set(distribution.map(item => item.name)).size !== 10
    || distribution.some(item => typeof item.longitude !== 'number' || !Number.isFinite(item.longitude))) {
    return '数据不足，未判定';
  }
  const rows = distribution.map((item) => {
    const signIndex = Math.floor(jonesGeometry.normalizedLongitude(item.longitude) / 30);
    return { name: item.name, element: signIndex % 4, modality: signIndex % 3 };
  });
  const elementCounts = [0, 0, 0, 0];
  const modalityCounts = [0, 0, 0];
  rows.forEach((row) => {
    elementCounts[row.element] += 1;
    modalityCounts[row.modality] += 1;
  });
  const labels = rows.map((row) => {
    const reasons = [];
    if (elementCounts[row.element] === 1) reasons.push(`唯一${ELEMENT_NAMES[row.element]}`);
    if (modalityCounts[row.modality] === 1) reasons.push(`唯一${MODALITY_NAMES[row.modality]}`);
    return reasons.length ? `${row.name}（${reasons.join('、')}）` : '';
  }).filter(Boolean);
  return labels.length ? labels.join('；') : '未发现';
}

function buildFocusNote(raw, keyRoles, context) {
  if (
    !raw
    || raw.pattern_en !== 'Splash'
    || raw.high_focus_planet
    || (keyRoles || []).length
  ) return null;
  const details = context || {};
  return {
    title: '无单一几何焦点',
    description: '以下是格局之外的辅助观察项，不等同于本格局的重点行星。',
    items: [
      { label: '命主星', hint: '上升星座的守护星', value: chartRulerText(details) },
      { label: '合轴星', hint: '距上升、下降、中天或天底前后3°以内', value: angularPlanetText(raw, details.aspects) },
      { label: '独聚星', hint: '十颗行星中，元素或模式唯一', value: singletonText(raw) },
    ].map(item => ({
      ...item,
      entries: /^(未发现|数据不足)/.test(item.value) ? [] : item.value.split(/[；／]/).map(text => {
        const parts = text.replace(/）$/, '').split('（');
        return { name: parts[0], detail: parts[1] || '' };
      }),
    })),
  };
}

function build(raw, ascLongitude, cusps, context) {
  if (!raw || !raw.pattern_en) return null;
  const keyRoles = (raw.key_roles || [])
    .map((role) => ({
      ...role,
      ...withPartners(role),
      positionText: jonesGeometry.formatSignDegree(role.longitude),
      isCore: rolePriority(role.role_type) === 0,
    }))
    .sort((a, b) => rolePriority(a.role_type) - rolePriority(b.role_type));
  const importantNames = keyRoles.reduce(
    (names, role) => names.concat([role.planet_name], role.partnerNames || []), []
  );
  const points = jonesGeometry.layoutDisplayPoints(
    raw.distribution, ascLongitude, importantNames
  );
  const bowlPoles = jonesGeometry.buildBowlPoles(
    raw.pattern_en,
    raw.midpoint_bowl,
    raw.cog_bowl,
    ascLongitude,
    raw.midpoint_loco,
    raw.midpoint_bundle
  ).concat(
    jonesGeometry.buildFocusGeometry(
      raw.pattern_en, raw.group_axis, raw.crossing_point, ascLongitude
    )
  );
  return {
    ...raw,
    points,
    occupiedFans: jonesGeometry.buildOccupiedFans(raw.distribution, raw.pattern_en, points),
    importantGap: jonesGeometry.buildImportantGap(raw.distribution),
    axisLabels: jonesGeometry.buildAxisLabels(cusps, ascLongitude),
    bowlPoles,
    keyRoles,
    focusNote: buildFocusNote(raw, keyRoles, { ...context, ascLongitude }),
    borderlineHint: buildBorderlineHint(raw),
    hasMovedPoints: points.some((point) => point.moved),
    ascLongitude: Number(ascLongitude || 0),
    cusps: (cusps || []).slice(0, 12),
    stateCopy: buildStateCopy(raw),
  };
}

module.exports = {
  build, buildStateCopy, buildFocusNote, buildBorderlineHint,
  angularPlanetText, singletonText, ROLE_PRIORITY,
};

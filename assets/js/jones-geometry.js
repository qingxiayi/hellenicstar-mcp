function normalizedLongitude(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return ((number % 360) + 360) % 360;
}

const ZODIAC_ZH = [
  '白羊座', '金牛座', '双子座', '巨蟹座', '狮子座', '处女座',
  '天秤座', '天蝎座', '射手座', '摩羯座', '水瓶座', '双鱼座',
];

/**
 * 占星语境的度分表示：星盘本身按"度+分"计算，文字描述也该跟着用这个格式
 * （比如"巨蟹座7°30'"），不能只写小数度（"97.5°"）——那是十进制黄经，
 * 不是占星读盘时会说的话。四舍五入到分，处理满60分进位/满30度进下一星座。
 */
function formatSignDegree(longitude) {
  const norm = normalizedLongitude(longitude);
  let signIndex = Math.min(Math.floor(norm / 30), 11);
  let posInSign = norm - signIndex * 30;
  let deg = Math.floor(posInSign);
  let min = Math.round((posInSign - deg) * 60);
  if (min === 60) { min = 0; deg += 1; }
  if (deg === 30) { deg = 0; signIndex = (signIndex + 1) % 12; }
  return `${ZODIAC_ZH[signIndex]}${deg}°${String(min).padStart(2, '0')}'`;
}

// Kept in parity with natal-chart/templates/index.html JONES_GROUP_COUNT.
const GROUP_COUNT = {
  Bowl: 1, Locomotive: 1, Bundle: 1, Splash: 1,
  Bucket: 2, Sling: 2, Fanhandle: 2, ConjHandle: 2, 'See-Saw': 2, Hourglass: 2,
  TwoHandle: 3, Tripod: 3, Splay: 3, Butterfly: 3,
};
const MIN_BREAK = 40;
const MIN_POINT_SEPARATION = 9;

function screenAngle(longitude, ascLongitude) {
  return normalizedLongitude(180 - normalizedLongitude(
    normalizedLongitude(longitude) - normalizedLongitude(ascLongitude)
  ));
}

function angularDistance(first, second) {
  return Math.abs(((first - second + 540) % 360) - 180);
}

/**
 * Match the original Jones mini-wheel: ASC at the left, close glyphs spread
 * along the circumference, and true positions retained for leader lines.
 */
function layoutDisplayPoints(distribution, ascLongitude, importantNames) {
  const marked = Array.isArray(importantNames) ? importantNames : [];
  const items = (distribution || []).map((item) => ({
    ...item,
    longitude: normalizedLongitude(item.longitude),
    trueAngle: screenAngle(item.longitude, ascLongitude),
  })).sort((a, b) => a.trueAngle - b.trueAngle);
  const count = items.length;
  if (!count) return [];

  let seamGap = -1;
  let seam = 0;
  for (let index = 0; index < count; index += 1) {
    const gap = index < count - 1
      ? items[index + 1].trueAngle - items[index].trueAngle
      : items[0].trueAngle + 360 - items[count - 1].trueAngle;
    if (gap > seamGap) { seamGap = gap; seam = (index + 1) % count; }
  }
  const sequence = items.slice(seam).concat(items.slice(0, seam));
  const base = sequence[0].trueAngle;
  const linear = sequence.map((item) => ({
    item,
    angle: normalizedLongitude(item.trueAngle - base),
  }));
  let groupStart = 0;
  while (groupStart < count) {
    let groupEnd = groupStart;
    while (
      groupEnd + 1 < count
      && linear[groupEnd + 1].angle - linear[groupEnd].angle < MIN_POINT_SEPARATION
    ) groupEnd += 1;
    const groupCount = groupEnd - groupStart + 1;
    if (groupCount > 1) {
      const mean = linear.slice(groupStart, groupEnd + 1)
        .reduce((sum, row) => sum + row.angle, 0) / groupCount;
      for (let index = groupStart; index <= groupEnd; index += 1) {
        linear[index].angle = mean
          + (index - groupStart - (groupCount - 1) / 2) * MIN_POINT_SEPARATION;
      }
    }
    groupStart = groupEnd + 1;
  }

  const byId = {};
  linear.forEach((row) => {
    const displayAngle = base + row.angle;
    const trueAngle = row.item.trueAngle;
    const displayRad = normalizedLongitude(displayAngle) * Math.PI / 180;
    const trueRad = trueAngle * Math.PI / 180;
    const glyphRadius = 43;
    // 真实黄经点刻意收在阴影扇形内部（阴影半径约占环半径 66%，参照 astro-seek
    // 实测行星圆点稳定落在环半径 55% 处），跟外圈可读字符圆区分开两层。
    const trueRadius = 26;
    const x = 50 + glyphRadius * Math.cos(displayRad);
    const y = 50 + glyphRadius * Math.sin(displayRad);
    const trueX = 50 + trueRadius * Math.cos(trueRad);
    const trueY = 50 + trueRadius * Math.sin(trueRad);
    const dx = x - trueX;
    const dy = y - trueY;
    byId[row.item.id] = {
      ...row.item,
      displayAngle,
      x: x.toFixed(3),
      y: y.toFixed(3),
      trueX: trueX.toFixed(3),
      trueY: trueY.toFixed(3),
      lineLength: Math.sqrt(dx * dx + dy * dy).toFixed(3),
      lineAngle: (Math.atan2(dy, dx) * 180 / Math.PI).toFixed(3),
      moved: angularDistance(displayAngle, trueAngle) > 1.5,
      focus: marked.indexOf(row.item.name) !== -1,
    };
  });
  return (distribution || []).map((item) => byId[item.id]);
}

function buildImportantGap(distribution) {
  const ordered = (distribution || []).map((item) => normalizedLongitude(item.longitude))
    .sort((a, b) => a - b);
  if (ordered.length < 2) return null;
  let start = ordered[0];
  let gap = -1;
  ordered.forEach((longitude, index) => {
    const next = ordered[(index + 1) % ordered.length];
    const current = (next - longitude + 360) % 360;
    if (current > gap) { start = longitude; gap = current; }
  });
  return { start, arc: gap, label: `${Math.round(gap)}°` };
}

/** Return occupied fan spans, split at the same gaps as the original web UI. */
function buildOccupiedFans(distribution, pattern, displayPoints) {
  const ordered = (distribution || []).map((item) => ({
    id: item.id,
    longitude: normalizedLongitude(item.longitude),
  })).sort((a, b) => a.longitude - b.longitude);
  const count = ordered.length;
  if (count < 2) return [];

  const gaps = ordered.map((item, index) => (
    ordered[(index + 1) % count].longitude - item.longitude + 360
  ) % 360);
  const ranked = gaps.map((gap, index) => ({ gap, index }))
    .sort((a, b) => b.gap - a.gap);
  const wanted = GROUP_COUNT[pattern] || 1;
  const breaks = new Set();
  for (let rank = 0; rank < ranked.length && breaks.size < wanted; rank += 1) {
    const candidate = ranked[rank];
    if (rank === 0 || candidate.gap >= MIN_BREAK) breaks.add(candidate.index);
  }

  let startIndex = 0;
  for (let index = 0; index < count; index += 1) {
    if (breaks.has(index)) { startIndex = (index + 1) % count; break; }
  }
  const fans = [];
  const displayById = {};
  (displayPoints || []).forEach((point) => { displayById[point.id] = point.displayAngle; });
  const pushFan = (items) => {
    if (items.length < 2) return;
    if (displayPoints) {
      const angles = items.map((item) => displayById[item.id])
        .filter((angle) => Number.isFinite(angle)).sort((a, b) => a - b);
      if (angles.length >= 2) fans.push({
        startAngle: angles[0],
        arc: angles[angles.length - 1] - angles[0],
      });
      return;
    }
    fans.push({
      start: items[0].longitude,
      arc: items[items.length - 1].longitude - items[0].longitude,
    });
  };
  let run = [];
  let previous = null;
  for (let step = 0; step < count; step += 1) {
    const index = (startIndex + step) % count;
    let longitude = ordered[index].longitude;
    if (previous != null) {
      while (longitude < previous) longitude += 360;
    }
    run.push({ ...ordered[index], longitude });
    previous = longitude;
    if (breaks.has(index)) {
      pushFan(run);
      run = [];
      previous = null;
    }
  }
  pushFan(run);
  return fans;
}

/** Percentage position (cx=cy=50) for a longitude at a given radius from center. */
function ringLabelPosition(longitude, ascLongitude, radius) {
  const angle = screenAngle(longitude, ascLongitude) * Math.PI / 180;
  return {
    x: (50 + radius * Math.cos(angle)).toFixed(3),
    y: (50 + radius * Math.sin(angle)).toFixed(3),
  };
}

/**
 * Four chart angles (ASC/DSC/MC/IC), placed at their true screen angle.
 * ASC/DSC are always exactly 180°/0° by definition (screenAngle's own
 * convention), but MC/IC's angular offset from ASC varies with latitude —
 * they must use real cusp longitudes, not a fixed top/bottom position.
 */
function buildAxisLabels(cusps, ascLongitude) {
  if (!Array.isArray(cusps) || cusps.length < 12) return [];
  const defs = [
    { id: 'asc', label: 'ASC', longitude: cusps[0] },
    { id: 'dsc', label: 'DSC', longitude: cusps[6] },
    { id: 'mc', label: 'MC', longitude: cusps[9] },
    { id: 'ic', label: 'IC', longitude: cusps[3] },
  ];
  // Keep labels just inside the ring. The shell intentionally clips overflow,
  // so the old 58% radius could place their centers at -8% / 108% and hide them.
  return defs.map((item) => ({ ...item, ...ringLabelPosition(item.longitude, ascLongitude, 47) }));
}

/**
 * Void-point (Bowl/Bucket/Locomotive/Bundle) and bowl-bottom (cog) virtual
 * geometry points supplied by the migrated Jones engine. The Bucket midpoint
 * must come from the nine-planet bowl boundaries; deriving it again from all
 * ten displayed planets would let the handle split the void.
 */
function buildBowlPoles(pattern, midpointBowl, cogBowl, ascLongitude, midpointLoco, midpointBundle) {
  const source = pattern === 'Bowl' || pattern === 'Bucket' ? midpointBowl
    : pattern === 'Locomotive' ? midpointLoco
    : pattern === 'Bundle' ? midpointBundle
    : null;
  const midpointValue = source && source.long != null ? Number(source.long) : NaN;
  if (!Number.isFinite(midpointValue)) return [];
  const voidLong = normalizedLongitude(midpointValue);
  // 虚点＝承重墙正对面、空白区的几何中点。Rudhyar 原话：意识里的「阴影」/未开垦的潜能区，
  // 是持续凝视、驱使去填补的一片真空——跟承重墙（既有的资源）互为一组对子。
  // 注：公开文案禁词表（备案要求）＝你/性格/人格/命运/人生/使命/职业/心理/能量，
  // 下面两条 description 是直接展示给用户的文案，改动时留意别踩回去。
  const poles = [{
    id: 'void',
    label: '虚点',
    longitude: voidLong,
    description: '空白区的几何中点，Rudhyar 称为意识里的「阴影」：不是空无，而是持续凝视、驱使去填补的一片真空。',
  }];
  // 碗底/占据半球重心：Bowl 与 Bucket（碗+把手）底层半球几何相通，都可能有承重墙星。
  if (pattern === 'Bowl' || pattern === 'Bucket') {
    const cogValue = cogBowl && cogBowl.long != null ? Number(cogBowl.long) : NaN;
    if (Number.isFinite(cogValue)) {
      const label = cogBowl.planet_name
        ? (cogBowl.is_anchor ? '碗底锚点' : '承重墙')
        : '碗底';
      const partnerNames = (cogBowl.partners || []).map(p => p && p.planet_name).filter(Boolean);
      const composite = cogBowl.planet_name && partnerNames.length
        ? `此处由${[cogBowl.planet_name].concat(partnerNames).join('与')}合相共同坐镇，两星一起看。`
        : '';
      poles.push({
        id: 'cog',
        label,
        longitude: normalizedLongitude(cogValue),
        description: '正对虚点的占据半球几何重心，是这张盘最深的资源储备与安全感锚点，用来填补对面那片虚空。' + composite,
      });
    }
  }
  return poles.map((item) => ({
    ...item,
    positionText: formatSignDegree(item.longitude),
    ...ringLabelPosition(item.longitude, ascLongitude, 32),
  }));
}

/**
 * 焦点几何虚点（后端已算、此前前端不可见的半闭环）：
 *   - See-Saw / Hourglass：两组各自的几何重心（group_axis.center_a/center_b），
 *     份量更重的一端加 ★ 标记。回答「没有其他焦点星时人生份量偏向哪一组」。
 *   - Butterfly：顶点星与较近一翼的隐藏交叉中点（crossing_point.long）。
 * 复用 buildBowlPoles 同一套渲染契约（label + positionText + 环上 x/y + description），
 * 直接并入 bowlPoles 数组，WXML 无需改动。
 * 注：description 是公开文案，须避开备案禁词表（你/性格/人格/命运/人生/使命/职业/心理/能量）。
 */
function buildFocusGeometry(pattern, groupAxis, crossingPoint, ascLongitude) {
  const points = [];
  if ((pattern === 'See-Saw' || pattern === 'Hourglass') && groupAxis) {
    // 先判 != null 再转（同 buildBowlPoles）：Number(null)===0 且是有限数，
    // 光靠 isFinite 挡不住空值，会在白羊座 0° 画出假标记。
    const a = groupAxis.center_a != null ? Number(groupAxis.center_a) : NaN;
    const b = groupAxis.center_b != null ? Number(groupAxis.center_b) : NaN;
    if (Number.isFinite(a) && Number.isFinite(b)) {
      const heavier = groupAxis.heavier;
      points.push({
        id: 'group_a',
        label: heavier === 'a' ? '重心·甲组 ★' : '重心·甲组',
        longitude: normalizedLongitude(a),
        description: heavier === 'a'
          ? '甲组行星更多、或更紧密聚集，是两组重心连线里份量更重的一端。'
          : '甲组行星的几何重心，与乙组隔空对峙、交替主导。',
      });
      points.push({
        id: 'group_b',
        label: heavier === 'b' ? '重心·乙组 ★' : '重心·乙组',
        longitude: normalizedLongitude(b),
        description: heavier === 'b'
          ? '乙组行星更多、或更紧密聚集，是两组重心连线里份量更重的一端。'
          : '乙组行星的几何重心，与甲组隔空对峙、交替主导。',
      });
    }
  }
  if (pattern === 'Butterfly' && crossingPoint) {
    const c = crossingPoint.long != null ? Number(crossingPoint.long) : NaN;
    if (Number.isFinite(c)) {
      points.push({
        id: 'crossing',
        label: '交叉中点',
        longitude: normalizedLongitude(c),
        description: '顶点星与较近一翼之间的隐藏中点，聚焦力在此汇聚，值得留意。',
      });
    }
  }
  return points.map((item) => ({
    ...item,
    positionText: formatSignDegree(item.longitude),
    ...ringLabelPosition(item.longitude, ascLongitude, 32),
  }));
}

module.exports = {
  buildAxisLabels,
  buildBowlPoles,
  buildFocusGeometry,
  buildImportantGap,
  buildOccupiedFans,
  formatSignDegree,
  layoutDisplayPoints,
  normalizedLongitude,
  screenAngle,
};

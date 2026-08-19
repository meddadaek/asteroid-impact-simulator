/* ===========================================================================
   Localisation: English and Arabic.

   Markup carries `data-i18n` keys rather than text, so `apply()` can rewrite
   the whole interface in place. Arabic switches the document to RTL; the
   stylesheet handles mirroring from the `dir` attribute alone.

   Numbers stay in Western digits and units stay metric in both languages,
   which is what technical and scientific Arabic writing normally does.
   =========================================================================== */

const EN = {
  'app.title': 'ORBITAL SENTINEL',
  'app.tagline': 'near-earth object impact modelling',
  'boot.init': 'initialising',
  'boot.textures': 'loading nasa imagery',
  'boot.globe': 'building globe',
  'boot.service': 'contacting service',

  'mode.simple': 'Simple',
  'mode.astronomer': 'Astronomer',

  'group.impactor': 'Impactor',
  'group.entry': 'Entry',
  'group.impactPoint': 'Impact point',
  'group.realObject': 'Real object',
  'group.elements': 'Orbital elements',
  'group.tracking': 'Tracking quality',
  'group.historical': 'Historical',

  'field.diameter': 'Diameter',
  'field.diameterHint': '1 m — 20 km (logarithmic)',
  'field.composition': 'Composition',
  'field.velocity': 'Velocity',
  'field.velocityHint': '11.2 km/s escape — 72 km/s head-on limit',
  'field.angle': 'Entry angle',
  'field.angleHint': 'from the horizontal; 45° is most probable',
  'field.latitude': 'Latitude',
  'field.longitude': 'Longitude',
  'field.clones': 'Clones',
  'field.uncertaintyHint': 'sets the element error bars the Monte Carlo samples',

  'mat.comet': 'Porous comet · 500 kg/m³',
  'mat.carbonaceous': 'Carbonaceous · 1500',
  'mat.stony': 'Stony (S-type) · 3000',
  'mat.stony_iron': 'Stony-iron · 5000',
  'mat.iron': 'Iron (M-type) · 7800',

  'unc.precise': 'Decades of radar tracking',
  'unc.good': 'Well observed, multi-apparition',
  'unc.moderate': 'Several months of observation',
  'unc.poor': 'Newly discovered, short arc',

  'note.clickGlobe': 'Click anywhere on the globe to place it.',
  'note.searchNeo': 'search 42,000 catalogued NEOs',
  'note.forceImpact': 'If it misses, show where it <em>would</em> have struck',
  'note.surrogate': 'The gradient-boosted surrogate answers in microseconds; ' +
    'the analytic solution is what it was fitted to. Both are shown so the ' +
    "model's error stays visible.",
  'note.noRings': 'No damage rings reach the ground.',
  'note.noCity': 'No catalogued city within the damage radius.',
  'note.atSea': 'The impact is at sea.',
  'note.nothingMatches': 'Nothing matches.',

  'btn.run': 'RUN SIMULATION',

  'preset.chelyabinsk': 'Chelyabinsk 2013',
  'preset.tunguska': 'Tunguska 1908',
  'preset.barringer': 'Barringer',
  'preset.chicxulub': 'Chicxulub',

  'view.earth': 'Earth',
  'view.orbit': 'Orbit',

  'res.outcome': 'outcome',
  'res.simpleMode': 'simple mode',
  'res.orbitSolution': 'orbit solution',
  'res.airburst': 'Airburst',
  'res.cratering': 'Cratering impact',
  'res.surface': 'Surface impact',
  'res.noImpact': 'No impact in 30 years',
  'res.clear': 'clear',
  'res.clearBody': 'This orbit does not intersect Earth inside the simulated window.',
  'res.site': 'Impact site',
  'res.rings': 'Damage rings',
  'res.exposed': 'Population exposed',
  'res.encounter': 'Encounter',
  'res.probability': 'Impact probability',
  'res.modelCheck': 'Surrogate vs physics',
  'res.hypothetical': 'This orbit misses — shown as a hypothetical strike.',
  'res.hiroshima': 'Equivalent to {n} Hiroshima bombs.',
  'res.totalUrban': 'Total in urban areas',

  'stat.energy': 'Energy',
  'stat.burstAltitude': 'Burst altitude',
  'stat.impactSpeed': 'Impact speed',
  'stat.crater': 'Crater',
  'stat.seismic': 'Seismic',
  'stat.fireball': 'Fireball',
  'stat.mass': 'Mass',
  'stat.none': 'none',

  'ro.coordinates': 'coordinates',
  'ro.terrain': 'terrain',
  'ro.bearing': 'bearing',
  'ro.nearest': 'nearest',
  'ro.surface': 'surface',
  'ro.land': 'land',
  'ro.ocean': 'ocean',
  'ro.perihelion': 'perihelion',
  'ro.aphelion': 'aphelion',
  'ro.period': 'period',
  'ro.moid': 'MOID',
  'ro.closestApproach': 'closest approach',
  'ro.lunarDistances': 'in lunar distances',
  'ro.vInfinity': 'v-infinity',
  'ro.outcome': 'outcome',
  'ro.impact': 'IMPACT',
  'ro.miss': 'miss',
  'ro.mlRisk': 'ML risk score',

  'mt.quantity': 'quantity',
  'mt.physics': 'physics',
  'mt.surrogate': 'surrogate',
  'mt.err': 'err',

  'cmp.energyReleased': 'Energy released',
  'cmp.burstAltitude': 'Burst altitude',
  'cmp.craterDiameter': 'Crater diameter',
  'cmp.homesCollapse': 'Houses collapse',
  'cmp.treesFlattened': 'Trees flattened',
  'cmp.windowsShatter': 'Windows shatter',
  'cmp.burns3rd': 'Third-degree burns',
  'cmp.seismicMagnitude': 'Seismic magnitude',

  'ring.total_destruction': 'Total destruction',
  'ring.concrete_fails': 'Reinforced buildings fail',
  'ring.homes_collapse': 'Houses collapse',
  'ring.burns_3rd': 'Third-degree burns',
  'ring.trees_flattened': 'Trees flattened',
  'ring.windows_shatter': 'Windows shatter',

  'sev.negligible': 'negligible',
  'sev.local': 'local',
  'sev.city': 'city',
  'sev.regional': 'regional',
  'sev.continental': 'continental',
  'sev.global': 'global',
  'sev.extinction': 'extinction',
  'sevDesc.negligible': 'Burns up high in the atmosphere. A bright fireball, nothing more.',
  'sevDesc.local': 'Airburst audible and visible for hundreds of kilometres. Broken windows.',
  'sevDesc.city': 'Destroys a metropolitan area. Comparable to the largest nuclear weapons.',
  'sevDesc.regional': 'Devastates a region the size of a small country.',
  'sevDesc.continental': 'Continental-scale destruction and multi-year climate disruption.',
  'sevDesc.global': 'Global catastrophe. Mass extinction territory.',
  'sevDesc.extinction': 'Sterilising impact. Larger than anything in the geological record.',

  'mc.struck': '{k} of {n} propagated clones struck Earth within {y} years.',
  'mc.interval': '95% interval {lo}% – {hi}%.',
  'mc.closest': 'Closest clone passed {d} km from Earth.',

  'err.backend': 'Backend unreachable: {msg}',
  'err.noModels': 'Models not trained yet — physics still works. Run app/train.py.',
  'err.failed': 'Simulation failed',
  'err.catalogue': 'Catalogue unavailable: {msg}',

  'unit.km': 'km', 'unit.m': 'm', 'unit.kms': 'km/s', 'unit.kg': 'kg',
  'unit.yr': 'yr', 'unit.au': 'AU', 'unit.ld': 'LD', 'unit.mt': 'Mt',
  'unit.kt': 'kt', 'unit.tt': 'Tt', 'unit.bn': 'bn', 'unit.M': 'M', 'unit.k': 'k',
  'timing.roundTrip': 'round trip {ms} ms',
};

const AR = {
  'app.title': 'الحارس المداري',
  'app.tagline': 'نمذجة ارتطام الأجرام القريبة من الأرض',
  'boot.init': 'جارٍ التهيئة',
  'boot.textures': 'تحميل صور ناسا',
  'boot.globe': 'بناء الكرة الأرضية',
  'boot.service': 'الاتصال بالخادم',

  'mode.simple': 'مبسّط',
  'mode.astronomer': 'فلكي',

  'group.impactor': 'الجرم المرتطم',
  'group.entry': 'الدخول',
  'group.impactPoint': 'نقطة الارتطام',
  'group.realObject': 'جرم حقيقي',
  'group.elements': 'العناصر المدارية',
  'group.tracking': 'جودة الرصد',
  'group.historical': 'أحداث تاريخية',

  'field.diameter': 'القطر',
  'field.diameterHint': '١ م — ٢٠ كم (مقياس لوغاريتمي)',
  'field.composition': 'التركيب',
  'field.velocity': 'السرعة',
  'field.velocityHint': '11.2 كم/ث سرعة الإفلات — 72 كم/ث الحد الأقصى',
  'field.angle': 'زاوية الدخول',
  'field.angleHint': 'من الأفق؛ 45° هي الأكثر احتمالاً',
  'field.latitude': 'خط العرض',
  'field.longitude': 'خط الطول',
  'field.clones': 'النسخ',
  'field.uncertaintyHint': 'يحدد هوامش خطأ العناصر التي تعاينها محاكاة مونت كارلو',

  'mat.comet': 'مذنب مسامي · 500 كغ/م³',
  'mat.carbonaceous': 'كربوني · 1500',
  'mat.stony': 'صخري · 3000',
  'mat.stony_iron': 'صخري حديدي · 5000',
  'mat.iron': 'حديدي · 7800',

  'unc.precise': 'عقود من التتبع الراداري',
  'unc.good': 'مرصود جيداً عبر ظهورات متعددة',
  'unc.moderate': 'عدة أشهر من الرصد',
  'unc.poor': 'مكتشف حديثاً، قوس رصد قصير',

  'note.clickGlobe': 'انقر في أي مكان على الكرة الأرضية لتحديد الموقع.',
  'note.searchNeo': 'ابحث في 42,000 جرم مفهرس',
  'note.forceImpact': 'إذا أخطأ الأرض، أظهر أين <em>كان</em> سيرتطم',
  'note.surrogate': 'النموذج البديل المعزز بالتدرج يجيب خلال ميكروثوانٍ، ' +
    'والحل التحليلي هو ما دُرِّب عليه. يُعرض الاثنان معاً ليبقى خطأ النموذج ظاهراً.',
  'note.noRings': 'لا تصل أي حلقات ضرر إلى سطح الأرض.',
  'note.noCity': 'لا توجد مدينة مفهرسة ضمن نطاق الضرر.',
  'note.atSea': 'الارتطام وقع في البحر.',
  'note.nothingMatches': 'لا توجد نتائج.',

  'btn.run': 'شغّل المحاكاة',

  'preset.chelyabinsk': 'تشيليابينسك 2013',
  'preset.tunguska': 'تونغوسكا 1908',
  'preset.barringer': 'فوهة بارينجر',
  'preset.chicxulub': 'تشيكشولوب',

  'view.earth': 'الأرض',
  'view.orbit': 'المدار',

  'res.outcome': 'النتيجة',
  'res.simpleMode': 'الوضع المبسّط',
  'res.orbitSolution': 'حل مداري',
  'res.airburst': 'انفجار جوي',
  'res.cratering': 'ارتطام محدث لفوهة',
  'res.surface': 'ارتطام سطحي',
  'res.noImpact': 'لا ارتطام خلال 30 سنة',
  'res.clear': 'آمن',
  'res.clearBody': 'هذا المدار لا يتقاطع مع الأرض ضمن النافذة الزمنية المحاكاة.',
  'res.site': 'موقع الارتطام',
  'res.rings': 'حلقات الضرر',
  'res.exposed': 'السكان المعرضون',
  'res.encounter': 'اللقاء القريب',
  'res.probability': 'احتمال الارتطام',
  'res.modelCheck': 'النموذج البديل مقابل الفيزياء',
  'res.hypothetical': 'هذا المدار يخطئ الأرض — معروض كارتطام افتراضي.',
  'res.hiroshima': 'يعادل {n} قنبلة من قنابل هيروشيما.',
  'res.totalUrban': 'الإجمالي في المناطق الحضرية',

  'stat.energy': 'الطاقة',
  'stat.burstAltitude': 'ارتفاع الانفجار',
  'stat.impactSpeed': 'سرعة الارتطام',
  'stat.crater': 'الفوهة',
  'stat.seismic': 'الزلزالية',
  'stat.fireball': 'كرة النار',
  'stat.mass': 'الكتلة',
  'stat.none': 'لا شيء',

  'ro.coordinates': 'الإحداثيات',
  'ro.terrain': 'التضاريس',
  'ro.bearing': 'الاتجاه',
  'ro.nearest': 'الأقرب',
  'ro.surface': 'السطح',
  'ro.land': 'يابسة',
  'ro.ocean': 'محيط',
  'ro.perihelion': 'الحضيض',
  'ro.aphelion': 'الأوج',
  'ro.period': 'الدورة',
  'ro.moid': 'أدنى مسافة بين المدارين',
  'ro.closestApproach': 'أقرب اقتراب',
  'ro.lunarDistances': 'بوحدات المسافة القمرية',
  'ro.vInfinity': 'السرعة اللانهائية',
  'ro.outcome': 'النتيجة',
  'ro.impact': 'ارتطام',
  'ro.miss': 'إخطاء',
  'ro.mlRisk': 'درجة الخطورة (تعلّم آلي)',

  'mt.quantity': 'الكمية',
  'mt.physics': 'الفيزياء',
  'mt.surrogate': 'النموذج البديل',
  'mt.err': 'الخطأ',

  'cmp.energyReleased': 'الطاقة المنبعثة',
  'cmp.burstAltitude': 'ارتفاع الانفجار',
  'cmp.craterDiameter': 'قطر الفوهة',
  'cmp.homesCollapse': 'انهيار المنازل',
  'cmp.treesFlattened': 'تسطّح الأشجار',
  'cmp.windowsShatter': 'تحطّم النوافذ',
  'cmp.burns3rd': 'حروق من الدرجة الثالثة',
  'cmp.seismicMagnitude': 'شدة الزلزال',

  'ring.total_destruction': 'دمار كامل',
  'ring.concrete_fails': 'انهيار المباني المسلحة',
  'ring.homes_collapse': 'انهيار المنازل',
  'ring.burns_3rd': 'حروق من الدرجة الثالثة',
  'ring.trees_flattened': 'تسطّح الأشجار',
  'ring.windows_shatter': 'تحطّم النوافذ',

  'sev.negligible': 'مهمل',
  'sev.local': 'محلي',
  'sev.city': 'مدينة',
  'sev.regional': 'إقليمي',
  'sev.continental': 'قاري',
  'sev.global': 'عالمي',
  'sev.extinction': 'انقراض',
  'sevDesc.negligible': 'يحترق عالياً في الغلاف الجوي. كرة نار ساطعة، لا أكثر.',
  'sevDesc.local': 'انفجار جوي يُسمع ويُرى لمئات الكيلومترات. نوافذ محطمة.',
  'sevDesc.city': 'يدمر منطقة حضرية كاملة. يضاهي أكبر الأسلحة النووية.',
  'sevDesc.regional': 'يدمر إقليماً بحجم دولة صغيرة.',
  'sevDesc.continental': 'دمار على مستوى قارة واضطراب مناخي يمتد سنوات.',
  'sevDesc.global': 'كارثة عالمية. في نطاق الانقراض الجماعي.',
  'sevDesc.extinction': 'ارتطام معقّم للحياة. أكبر من أي شيء في السجل الجيولوجي.',

  'mc.struck': 'ارتطمت {k} نسخة من أصل {n} بالأرض خلال {y} سنة.',
  'mc.interval': 'مجال ثقة 95%: {lo}% – {hi}%.',
  'mc.closest': 'أقرب نسخة مرّت على بعد {d} كم من الأرض.',

  'err.backend': 'تعذّر الوصول إلى الخادم: {msg}',
  'err.noModels': 'النماذج غير مدرَّبة بعد — الفيزياء تعمل. شغّل app/train.py.',
  'err.failed': 'فشلت المحاكاة',
  'err.catalogue': 'الفهرس غير متاح: {msg}',

  'unit.km': 'كم', 'unit.m': 'م', 'unit.kms': 'كم/ث', 'unit.kg': 'كغ',
  'unit.yr': 'سنة', 'unit.au': 'و.ف', 'unit.ld': 'م.ق', 'unit.mt': 'ميغاطن',
  'unit.kt': 'كيلوطن', 'unit.tt': 'تيراطن', 'unit.bn': 'مليار',
  'unit.M': 'مليون', 'unit.k': 'ألف',
  'timing.roundTrip': 'زمن الاستجابة {ms} م.ث',
};

const DICTS = { en: EN, ar: AR };
let current = localStorage.getItem('os-lang') || 'en';

/** Translate a key, substituting {placeholders}. Falls back to English. */
export function t(key, vars) {
  const dict = DICTS[current] || EN;
  let s = dict[key] !== undefined ? dict[key] : (EN[key] !== undefined ? EN[key] : key);
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(v);
  }
  return s;
}

export function lang() { return current; }
export function isRTL() { return current === 'ar'; }

export function setLang(next) {
  current = DICTS[next] ? next : 'en';
  localStorage.setItem('os-lang', current);
  apply();
}

/** Rewrite every tagged node in the document. */
export function apply() {
  document.documentElement.lang = current;
  document.documentElement.dir = isRTL() ? 'rtl' : 'ltr';

  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.innerHTML = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.title = t(el.dataset.i18nTitle);
  });
  document.querySelectorAll('.lang-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === current);
  });
  document.dispatchEvent(new CustomEvent('langchange', { detail: current }));
}

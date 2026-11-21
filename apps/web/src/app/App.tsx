import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { isConfigured, loadProfile, supabase } from './auth';
import AcademicPage from './AcademicPage';
import { LiveActivity, LiveDashboard, useDashboard } from './DashboardLive';
import type { Profile } from './auth';
import type { CSSProperties, ReactNode } from 'react';

type IconName = 'grid' | 'route' | 'book' | 'chart' | 'spark' | 'check' | 'award' | 'users' | 'layers' | 'network' | 'bell' | 'settings' | 'search' | 'chevron' | 'arrow' | 'menu' | 'pause' | 'play' | 'reset' | 'calendar' | 'filter' | 'clock' | 'more' | 'download' | 'target' | 'activity' | 'shield' | 'bolt' | 'close' | 'external' | 'message' | 'sun' | 'moon' | 'logout' | 'mail' | 'lock' | 'eye' | 'eyeOff';
const iconPaths: Record<IconName, ReactNode> = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.6"/><rect x="14" y="3" width="7" height="7" rx="1.6"/><rect x="3" y="14" width="7" height="7" rx="1.6"/><rect x="14" y="14" width="7" height="7" rx="1.6"/></>,
  route: <><circle cx="6" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="M8 6h7a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h7"/></>,
  book: <><path d="M4 5.5C7 4 9 4 12 6v14c-3-2-5-2-8-.5V5.5ZM20 5.5c-3-1.5-5-1.5-8 .5v14c3-2 5-2 8-.5V5.5Z"/></>,
  chart: <><path d="M4 20h16M6 16v-5M11 16V5M16 16v-8M21 16v-4"/></>,
  spark: <><path d="m12 2 1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2ZM19 17l.7 2.3L22 20l-2.3.7L19 23l-.7-2.3L16 20l2.3-.7L19 17Z"/></>,
  check: <><path d="m5 12 4 4L19 6"/></>,
  award: <><circle cx="12" cy="8" r="5"/><path d="m8 12-2 9 6-3 6 3-2-9"/></>,
  users: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2H3ZM17 5a3 3 0 0 1 0 6M17 15a5 5 0 0 1 4 5"/></>,
  layers: <><path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5"/></>,
  network: <><circle cx="5" cy="12" r="2"/><circle cx="12" cy="4" r="2"/><circle cx="19" cy="9" r="2"/><circle cx="17" cy="19" r="2"/><path d="m6.4 10.5 4.3-5M13.8 4.7l3.4 3M18.6 11l-1.2 6M6.7 13.1l8.6 4.8"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="m10 2-.5 2.2-2 1-2.1-.9-2 3.5 1.7 1.5v2.4l-1.7 1.5 2 3.5 2.1-.9 2 1L10 20h4l.5-2.2 2-1 2.1.9 2-3.5-1.7-1.5v-2.4l1.7-1.5-2-3.5-2.1.9-2-1L14 2h-4Z"/></>,
  search: <><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4 4"/></>,
  chevron: <><path d="m7 10 5 5 5-5"/></>, arrow: <><path d="M4 12h16m-6-6 6 6-6 6"/></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16"/></>,
  pause: <><path d="M8 5v14M16 5v14"/></>, play: <><path d="m8 5 11 7-11 7V5Z"/></>, reset: <><path d="M4 12a8 8 0 1 0 2-5.3M4 4v4h4"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/></>,
  filter: <><path d="M3 5h18l-7 8v6l-4 2v-8L3 5Z"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  download: <><path d="M12 3v13m-5-5 5 5 5-5M4 18v3h16v-3"/></>,
  target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></>,
  activity: <><path d="M2 12h4l3-7 5 14 3-7h5"/></>,
  shield: <><path d="m12 2 8 3v6c0 5-3 8-8 11-5-3-8-6-8-11V5l8-3Z"/><path d="m9 12 2 2 4-4"/></>,
  bolt: <><path d="m13 2-9 11h7l-1 9 10-12h-7V2Z"/></>,
  close: <><path d="M5 5 19 19M19 5 5 19"/></>,
  external: <><path d="M13 4h7v7M20 4l-9 9M20 14v6H4V4h6"/></>,
  message: <><path d="M4 4h16v12H8l-4 4V4Z"/></>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/></>,
  moon: <><path d="M20.5 14.4A8.8 8.8 0 0 1 9.6 3.5 8.8 8.8 0 1 0 20.5 14.4Z"/></>,
  logout: <><path d="M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M14 7l5 5-5 5m5-5H9"/></>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/></>,
  lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 15v2"/></>,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>,
  eyeOff: <><path d="m3 3 18 18M10.6 5.1A12 12 0 0 1 12 5c6 0 10 7 10 7a16 16 0 0 1-3.2 3.8M6.3 6.3C3.6 8.1 2 12 2 12s4 7 10 7a9.4 9.4 0 0 0 4.1-.9M10 10a3 3 0 0 0 4 4"/></>,
};
function Icon({ name, size = 19, className = '' }: { name: IconName; size?: number; className?: string }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconPaths[name]}</svg>;
}

type NavItem = { id: string; label: string; icon: IconName; group: 'principal' | 'academico' | 'inteligencia' | 'sistema' };
const navigation: NavItem[] = [
  { id: 'dashboard', label: 'Resumen general', icon: 'grid', group: 'principal' },
  { id: 'paths', label: 'Rutas de aprendizaje', icon: 'route', group: 'academico' },
  { id: 'courses', label: 'Cursos y contenidos', icon: 'book', group: 'academico' },
  { id: 'assessments', label: 'Evaluaciones', icon: 'check', group: 'academico' },
  { id: 'certificates', label: 'Certificados', icon: 'award', group: 'academico' },
  { id: 'community', label: 'Comunidad', icon: 'users', group: 'academico' },
  { id: 'analytics', label: 'Analítica educativa', icon: 'chart', group: 'inteligencia' },
  { id: 'skills', label: 'Dominio de habilidades', icon: 'layers', group: 'inteligencia' },
  { id: 'tutor', label: 'IA Tutor', icon: 'spark', group: 'inteligencia' },
  { id: 'neural', label: 'Red neuronal', icon: 'network', group: 'inteligencia' },
  { id: 'recommendations', label: 'Recomendaciones', icon: 'bolt', group: 'inteligencia' },
  { id: 'activity', label: 'Actividad y avisos', icon: 'bell', group: 'sistema' },
  { id: 'admin', label: 'Administración', icon: 'settings', group: 'sistema' },
];
const PAGE: Record<string, { title: string; eyebrow: string; desc: string }> = {
  dashboard: { title: 'Visión general', eyebrow: 'PANEL DE CONTROL', desc: 'Una mirada clara al aprendizaje y al progreso de tu institución.' },
  paths: { title: 'Rutas de aprendizaje', eyebrow: 'EXPERIENCIA ACADÉMICA', desc: 'Diseña itinerarios, define objetivos y acompaña cada etapa.' },
  courses: { title: 'Cursos y contenidos', eyebrow: 'EXPERIENCIA ACADÉMICA', desc: 'Explora los cursos y organiza el conocimiento de tu institución.' },
  assessments: { title: 'Evaluaciones', eyebrow: 'EXPERIENCIA ACADÉMICA', desc: 'Actividades, intentos, criterios y resultados en un solo lugar.' },
  certificates: { title: 'Certificados', eyebrow: 'EXPERIENCIA ACADÉMICA', desc: 'Reconoce logros y verifica cada credencial.' },
  community: { title: 'Comunidad', eyebrow: 'EXPERIENCIA ACADÉMICA', desc: 'Conversaciones que conectan a docentes y estudiantes.' },
  analytics: { title: 'Analítica educativa', eyebrow: 'INTELIGENCIA', desc: 'Señales y tendencias para comprender cómo se aprende.' },
  skills: { title: 'Dominio de habilidades', eyebrow: 'INTELIGENCIA', desc: 'Evidencias de aprendizaje por competencia y nivel.' },
  tutor: { title: 'IA Tutor', eyebrow: 'INTELIGENCIA', desc: 'Orientación personalizada con motivos claros y revisión humana.' },
  neural: { title: 'Arquitectura neuronal', eyebrow: 'INTELIGENCIA', desc: 'Explora visualmente las capas y el flujo de un modelo.' },
  recommendations: { title: 'Recomendaciones', eyebrow: 'INTELIGENCIA', desc: 'Próximos pasos sugeridos para cada ruta de aprendizaje.' },
  activity: { title: 'Actividad y avisos', eyebrow: 'SISTEMA', desc: 'Eventos recientes y notificaciones de la plataforma.' },
  admin: { title: 'Administración', eyebrow: 'SISTEMA', desc: 'Usuarios, permisos, instituciones y configuración.' },
};

const courses = [
  { id: '01', name: 'Fundamentos de inteligencia artificial', category: 'INTELIGENCIA ARTIFICIAL', people: 284, progress: 78, color: 'violet', symbol: '✦', initials: 'IA', duration: '12 horas' },
  { id: '02', name: 'Análisis de datos con Python', category: 'CIENCIA DE DATOS', people: 196, progress: 62, color: 'cyan', symbol: '⌘', initials: 'PY', duration: '18 horas' },
  { id: '03', name: 'Diseño de experiencias digitales', category: 'DISEÑO DIGITAL', people: 142, progress: 85, color: 'teal', symbol: '◈', initials: 'UX', duration: '10 horas' },
  { id: '04', name: 'Redes neuronales aplicadas', category: 'DEEP LEARNING', people: 98, progress: 46, color: 'orange', symbol: '◎', initials: 'RN', duration: '16 horas' },
];
const activities = [
  { icon: 'check' as IconName, tone: 'teal', title: 'Evaluación completada', detail: 'Fundamentos de inteligencia artificial', time: 'Hace 12 min' },
  { icon: 'book' as IconName, tone: 'cyan', title: 'Nueva lección publicada', detail: 'Análisis de datos con Python', time: 'Hace 48 min' },
  { icon: 'award' as IconName, tone: 'violet', title: 'Certificado emitido', detail: 'Diseño de experiencias digitales', time: 'Hace 2 h' },
  { icon: 'users' as IconName, tone: 'orange', title: 'Nueva matrícula registrada', detail: 'Redes neuronales aplicadas', time: 'Hace 4 h' },
];

function Demo({ compact = false }: { compact?: boolean }) { return <span className={`demo-tag ${compact ? 'demo-tag--small' : ''}`} title="Los datos de esta vista son ilustrativos">● DATOS DEMO</span>; }
function Panel({ title, eyebrow, action, children, className = '' }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-head"><div>{eyebrow && <span className="panel-eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>{action}</div>{children}</section>;
}
function TinyArrow() { return <span className="tiny-arrow"><Icon name="arrow" size={15}/></span>; }

function NeuralNetwork({ running, compact = false }: { running: boolean; compact?: boolean }) {
  const columns = [3, 5, 5, 3];
  const xs = [48, 155, 262, 369];
  const yFor = (count: number, index: number) => 122 + (index - (count - 1) / 2) * (compact ? 34 : 39);
  return <div className={`neural-scene ${running ? 'is-running' : 'is-paused'} ${compact ? 'neural-scene--compact' : ''}`}>
    <div className="scene-grid"/><div className="scene-orb scene-orb--one"/><div className="scene-orb scene-orb--two"/>
    <svg viewBox="0 0 418 244" role="img" aria-label="Ilustración de una red neuronal de cuatro capas con conexiones animadas">
      <defs><linearGradient id="linkGradient" x1="0" x2="1"><stop stopColor="#1877e8"/><stop offset=".55" stopColor="#36c9ee"/><stop offset="1" stopColor="#aa77ff"/></linearGradient><filter id="nodeGlow"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
      {columns.slice(0, -1).flatMap((count, col) => Array.from({ length: count }, (_, i) => columns[col + 1] ? Array.from({ length: columns[col + 1] }, (_, j) => <line key={`${col}-${i}-${j}`} className="neural-link" x1={xs[col]} y1={yFor(count, i)} x2={xs[col + 1]} y2={yFor(columns[col + 1], j)} style={{ animationDelay: `${(col * 5 + i + j) * 75}ms` }} />) : []))}
      {columns.flatMap((count, col) => Array.from({ length: count }, (_, i) => <g key={`${col}-${i}`}><circle className="neural-halo" cx={xs[col]} cy={yFor(count, i)} r="14"/><circle className={`neural-node neural-node--${col}`} cx={xs[col]} cy={yFor(count, i)} r="5.5" style={{ animationDelay: `${(col * 4 + i) * 90}ms` }}/></g>))}
    </svg>
    <div className="neural-labels"><span>Entrada<small>3 variables</small></span><span>Capa oculta<small>5 neuronas</small></span><span>Capa oculta<small>5 neuronas</small></span><span>Salida<small>3 objetivos</small></span></div>
    <div className="scene-corner scene-corner--tl"/><div className="scene-corner scene-corner--br"/>
  </div>;
}

function TrendChart({ period }: { period: string }) {
  const points = period === '7 días' ? [23, 27, 26, 34, 31, 43, 48] : period === '90 días' ? [20, 23, 22, 28, 25, 31, 33, 30, 38, 37, 43, 49] : [18, 22, 20, 28, 26, 31, 29, 36, 33, 38, 43, 47];
  const secondary = points.map((value, i) => value * .56 + 7 + Math.sin(i) * 2);
  const plot = (series: number[]) => series.map((y, i) => `${34 + i * (544 / (series.length - 1))},${158 - y * 2.25}`).join(' ');
  return <div className="chart-wrap"><div className="chart-y"><span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span></div><svg className="trend-chart" viewBox="0 0 612 190" preserveAspectRatio="none" role="img" aria-label="Tendencia ilustrativa de participación y finalización">
    <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#138bf3" stopOpacity=".28"/><stop offset="1" stopColor="#138bf3" stopOpacity="0"/></linearGradient></defs>
    {[29, 61, 93, 125, 157].map(y => <line key={y} className="chart-grid" x1="33" x2="605" y1={y} y2={y}/>)}
    <polygon fill="url(#area)" points={`34,170 ${plot(points)} 578,170`}/><polyline className="chart-line chart-line--blue" points={plot(points)}/><polyline className="chart-line chart-line--violet" points={plot(secondary)}/>
    <circle cx="578" cy={158 - points.at(-1)! * 2.25} r="5.5" fill="#47c9ff" stroke="#0b2543" strokeWidth="4"/>
  </svg><div className="chart-x"><span>Inicio</span><span>Semana 1</span><span>Semana 2</span><span>Semana 3</span><span>Hoy</span></div></div>;
}

function CompletionDonut() { return <div className="completion-layout"><div className="donut"><div className="donut-center"><strong>72%</strong><span>completado</span></div></div><div className="donut-legend"><div><i className="dot teal"/><span>Completados</span><strong>72%</strong></div><div><i className="dot blue"/><span>En progreso</span><strong>19%</strong></div><div><i className="dot muted"/><span>Sin iniciar</span><strong>9%</strong></div></div></div>; }
function LearningMap() {
  const spots = [{x:95,y:66,r:16},{x:120,y:88,r:8},{x:156,y:151,r:12},{x:250,y:72,r:13},{x:282,y:111,r:15},{x:347,y:90,r:19},{x:396,y:142,r:11},{x:449,y:78,r:9}];
  return <div className="learning-map"><svg viewBox="0 0 500 195" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Mapa ilustrativo de actividad académica por regiones, datos de demostración"><defs><pattern id="mapDots" width="5" height="5" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r=".85" fill="#2876b3"/></pattern><radialGradient id="spotGlow"><stop stopColor="#6cf7ff" stopOpacity=".9"/><stop offset=".3" stopColor="#139cfa" stopOpacity=".4"/><stop offset="1" stopColor="#1267c4" stopOpacity="0"/></radialGradient></defs><path className="map-continent" d="M33 46 65 27l35 3 20 11 15-10 29 10 3 17-13 8-16-5-17 14-12 2-8 27-19-8-16 6-12-18-16 1-12-22ZM112 112l30-7 23 11 11 22-16 24-10 27-18-8-8-19-17-15ZM220 39l28-12 27 5 17-15 41 5 38 12 35-5 28 22 35-1 13 28-21 11-16-9-13 19-37-11-20 13-27-4-11 24-27-3-17-19-14 4-27-15-14 7-17-18-24-4ZM239 106l36 5 25 20-8 24-18 29-24-7-12-23-11-22ZM400 148l33-10 35 13-5 21-29 11-29-14Z" fill="url(#mapDots)" stroke="#245e93" strokeWidth=".8"/>{spots.map((s,i)=><g key={i}><circle cx={s.x} cy={s.y} r={s.r*2.2} fill="url(#spotGlow)" className="map-aura" style={{animationDelay:`${i*.35}s`}}/><circle cx={s.x} cy={s.y} r="2.7" fill="#75f8ff" className="map-point" style={{animationDelay:`${i*.3}s`}}/></g>)}</svg><div className="map-stat map-stat--left"><strong>América</strong><span>8,450 · DEMO</span></div><div className="map-stat map-stat--right"><strong>Europa</strong><span>6,120 · DEMO</span></div><div className="map-stat map-stat--bottom"><strong>Asia</strong><span>7,390 · DEMO</span></div></div>;
}
function MasteryHeatmap() {
  const rows=['Inteligencia artificial','Análisis de datos','Ciencia de datos','Desarrollo web','Nube y DevOps'];
  const values=[[18,27,45,71,84],[25,38,58,73,88],[17,31,54,74,93],[22,41,65,79,85],[12,28,46,69,82]];
  return <div className="heatmap-layout"><div className="heatmap-labels">{rows.map((r,i)=><span key={r}><i style={{background:['#4ea4fa','#56cbed','#8c81f1','#b473e9','#d585dd'][i]}}/>{r}</span>)}</div><div className="heatmap-main"><div className="heatmap-cells">{values.flatMap((row,i)=>row.map((v,j)=><span key={`${i}-${j}`} title={`${rows[i]} · ${['Aprender','Practicar','Aplicar','Avanzado','Experto'][j]}: ${v}% DEMO`} style={{'--intensity':v/100,'--delay':`${(i*5+j)*.04}s`} as CSSProperties}/>))}</div><div className="heatmap-axis">{['Aprender','Practicar','Aplicar','Avanzado','Experto'].map(x=><span key={x}>{x}</span>)}</div></div><div className="heatmap-scale"><small>100%</small><span/><small>0%</small></div></div>;
}
function Kpi({ icon, value, label, delta, color, subtitle }: { icon: IconName; value: string; label: string; delta: string; color: string; subtitle: string }) {
  return <div className="kpi-card"><div className="kpi-top"><span className={`kpi-icon tone-${color}`}><Icon name={icon} size={21}/></span><span className="kpi-spark"><i/><i/><i/><i/><i/><i/><i/></span></div><div className="kpi-value">{value}</div><div className="kpi-label">{label}</div><div className="kpi-bottom"><span className="positive">↗ {delta}</span><span>{subtitle}</span></div></div>;
}

function FuturisticDashboard({onNavigate,running,onToggle,period,onPeriod}:{onNavigate:(id:string)=>void;running:boolean;onToggle:()=>void;period:string;onPeriod:(p:string)=>void}){
  return <div className="command-dashboard">
    <div className="command-grid-top">
      <Panel title="Arquitectura de aprendizaje inteligente" eyebrow="RED NEURONAL · DEMOSTRACIÓN" className="command-network" action={<span className="signal-badge"><i/> Vista DEMO</span>}>
        <div className="network-overline"><span>NIVEL DE ENTRADA</span><span>CAPAS OCULTAS</span><span>SALIDA</span></div>
        <NeuralNetwork compact running={running}/>
        <div className="network-actions"><span><Icon name="activity" size={14}/> Flujo ilustrativo de señales</span><button onClick={onToggle} className="small-control"><Icon name={running?'pause':'play'} size={13}/>{running?'Pausar':'Animar'}</button></div>
        <div className="command-kpis"><Kpi icon="users" value="2,847" label="Estudiantes" delta="12.8%" color="cyan" subtitle="DEMO"/><Kpi icon="book" value="48" label="Cursos" delta="6.2%" color="blue" subtitle="DEMO"/><Kpi icon="clock" value="18.4k" label="Horas de aprendizaje" delta="18.6%" color="violet" subtitle="DEMO"/><Kpi icon="award" value="1,203" label="Certificaciones" delta="9.4%" color="teal" subtitle="DEMO"/></div>
      </Panel>
      <Panel title="Progreso académico" eyebrow="ANÁLISIS DE APRENDIZAJE" className="command-trend" action={<button className="panel-icon-link" aria-label="Abrir analítica" onClick={()=>onNavigate('analytics')}><Icon name="arrow" size={15}/></button>}>
        <div className="chart-summary"><div><strong>76.4%</strong><span>Participación ilustrativa</span></div><span className="chart-change">↗ +12.5% vs. periodo anterior</span></div>
        <div className="command-chart-legend"><span><i className="dot blue"/> Participación</span><span><i className="dot violet"/> Finalización</span><div className="segmented">{['7 días','30 días','90 días'].map(p=><button key={p} className={period===p?'active':''} onClick={()=>onPeriod(p)}>{p}</button>)}</div></div>
        <TrendChart period={period}/><p className="chart-disclaimer">Datos DEMO · sin fuente institucional conectada</p>
      </Panel>
    </div>
    <div className="command-grid-middle">
      <Panel title="Mapa de progreso de aprendizaje" eyebrow="DISTRIBUCIÓN AGREGADA · DEMO" className="command-map" action={<button className="panel-icon-link" aria-label="Abrir analítica" onClick={()=>onNavigate('analytics')}><Icon name="arrow" size={15}/></button>}><LearningMap/></Panel>
      <Panel title="Finalización de cursos" eyebrow="ESTADO DE MATRÍCULAS · DEMO" className="command-donut"><CompletionDonut/><div className="microbars" aria-hidden="true">{[17,24,18,36,29,22,41,27,38,24,48,29,35,46,32,49,31,42,58,37,48,32,50,60,44,51,39,61,48,59].map((h,i)=><span key={i} style={{height:`${h}%`}}/>)}</div></Panel>
    </div>
    <div className="command-grid-bottom">
      <Panel title="Dominio de habilidades" eyebrow="MAPA DE CALOR · DEMO" className="command-heatmap" action={<button className="panel-icon-link" aria-label="Abrir dominio de habilidades" onClick={()=>onNavigate('skills')}><Icon name="arrow" size={15}/></button>}><MasteryHeatmap/></Panel>
      <Panel title="Recomendaciones de IA" eyebrow="PRÓXIMOS PASOS · DEMO" className="command-recommendations" action={<button className="panel-icon-link" aria-label="Abrir recomendaciones" onClick={()=>onNavigate('recommendations')}><Icon name="arrow" size={15}/></button>}><div className="command-reco-list">{[{t:'Repasa inteligencia artificial',s:'Recurso sugerido',icon:'spark' as IconName,tone:'violet'},{t:'Completa Machine Learning básico',s:'Actividad sugerida',icon:'play' as IconName,tone:'blue'},{t:'Sigue la ruta de ciencia de datos',s:'Ruta sugerida',icon:'route' as IconName,tone:'teal'},{t:'Explora nuevos cursos',s:'Catálogo disponible',icon:'book' as IconName,tone:'orange'}].map(x=><button key={x.t} onClick={()=>onNavigate('recommendations')}><span className={`tone-${x.tone}`}><Icon name={x.icon} size={14}/></span><div><strong>{x.t}</strong><small>{x.s}</small></div><Icon name="arrow" size={13}/></button>)}</div></Panel>
      <Panel title="Actividad reciente" eyebrow="ÚLTIMOS EVENTOS · DEMO" className="command-activity" action={<button className="text-link" onClick={()=>onNavigate('activity')}>Ver todas <Icon name="arrow" size={13}/></button>}><div className="command-activity-list">{activities.map(a=><div key={a.title}><span className={`tone-${a.tone}`}><Icon name={a.icon} size={13}/></span><div><strong>{a.title}</strong><small>{a.detail}</small></div><time>{a.time}</time></div>)}</div></Panel>
    </div>
    <div className="dashboard-bottom-note"><span><i/> APRENDE · PRACTICA · DESTACA</span><span>Interfaz de demostración · Los indicadores y la red neuronal aún no están conectados al backend</span></div>
  </div>;
}

const skillData = [{ name:'Pensamiento crítico',score:88,color:'teal'},{name:'Análisis de datos',score:76,color:'cyan'},{name:'Resolución de problemas',score:82,color:'violet'},{name:'Comunicación',score:64,color:'blue'}];
function SkillRows({compact=false}:{compact?:boolean}) { return <div className={`skill-rows ${compact?'skill-rows--compact':''}`}>{skillData.map(s=><div className="skill-row" key={s.name}><div><span>{s.name}</span><strong>{s.score}%</strong></div><div className="skill-track"><span className={`fill-${s.color}`} style={{width:`${s.score}%`}}/></div></div>)}<p className="muted-note">Valores ilustrativos. El nivel validado por docentes se mostrará por separado.</p></div>; }
function CourseCards({ search }: { search: string }) { const filtered = courses.filter(c => `${c.name} ${c.category}`.toLowerCase().includes(search.toLowerCase()));return filtered.length ? <div className="cards-grid">{filtered.map(c=><article className="course-card" key={c.id}><div className={`course-card-art art-${c.color}`}><span className="art-decoration">{c.symbol}</span><span className="art-chip">{c.initials}</span></div><div className="course-card-body"><span className="mini-overline">{c.category}</span><h3>{c.name}</h3><div className="course-meta"><span><Icon name="users" size={15}/>{c.people} estudiantes</span><span><Icon name="clock" size={15}/>{c.duration}</span></div><div className="course-card-bottom"><span>Progreso <strong>{c.progress}%</strong></span><div className="progress-track"><span style={{width:`${c.progress}%`}}/></div></div></div></article>)}</div> : <div className="empty-state"><Icon name="search" size={28}/><h3>No encontramos cursos</h3><p>Prueba con otro término de búsqueda.</p></div>; }
function OverviewTiles({ items }: { items: {icon:IconName; value:string; label:string; tone:string}[] }) {return <div className="mini-kpi-grid">{items.map(x=><div className="mini-kpi" key={x.label}><span className={`mini-kpi-icon tone-${x.tone}`}><Icon name={x.icon} size={20}/></span><strong>{x.value}</strong><small>{x.label}</small></div>)}</div>;}

function SecondaryPage({ section, onNavigate, running, onToggle }: { section: string; onNavigate: (id:string)=>void; running:boolean; onToggle:()=>void }) {
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState('');
  const demoAction = (message:string) => { setNotice(message); window.setTimeout(()=>setNotice(''),4200); };
  useEffect(()=>{setSearch('');setNotice('');},[section]);
  const onDemo = (label:string) => demoAction(`${label}: vista de demostración. Se conectará a la API en una próxima fase.`);
  return <div className="secondary-page">
    <div className="page-intro-card"><div><span className="intro-serial">EDUMASTER.AI / {section.toUpperCase().replaceAll('-', ' ')}</span><h2>{PAGE[section].title}</h2><p>{PAGE[section].desc}</p><Demo compact/></div><div className="intro-watermark"><Icon name={navigation.find(n=>n.id===section)?.icon??'grid'} size={90}/></div></div>
    {notice && <div className="toast" role="status"><Icon name="spark" size={17}/>{notice}<button aria-label="Cerrar aviso" onClick={()=>setNotice('')}><Icon name="close" size={16}/></button></div>}
    {section==='courses' && <><div className="toolbar"><div className="toolbar-search"><Icon name="search" size={18}/><input aria-label="Buscar cursos" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Buscar cursos o categorías..."/></div><button className="outline-button" onClick={()=>onDemo('Filtros')}><Icon name="filter" size={16}/> Filtros</button><button className="primary-button" onClick={()=>onDemo('Crear curso')}>+ Nuevo curso</button></div><CourseCards search={search}/></>}
    {section==='paths' && <><OverviewTiles items={[{icon:'route',value:'12',label:'Rutas diseñadas',tone:'cyan'},{icon:'users',value:'1,486',label:'Estudiantes inscritos',tone:'violet'},{icon:'target',value:'68%',label:'Avance promedio',tone:'teal'}]}/><div className="cards-grid">{[{title:'Ruta de Ciencia de Datos',sub:'4 cursos · Nivel intermedio',pct:68,color:'cyan'},{title:'Experiencia Digital',sub:'3 cursos · Nivel inicial',pct:82,color:'violet'},{title:'Fundamentos de IA',sub:'5 cursos · Nivel avanzado',pct:46,color:'teal'}].map((p,i)=><article className="path-card" key={p.title}><div className={`path-icon tone-${p.color}`}><Icon name="route" size={22}/></div><span className="path-index">RUTA / 0{i+1}</span><h3>{p.title}</h3><p>{p.sub}</p><div className="path-progress"><span>Progreso de la ruta</span><strong>{p.pct}%</strong></div><div className="progress-track"><span style={{width:`${p.pct}%`}}/></div><button className="text-link" onClick={()=>onDemo('Detalle de ruta')}>Explorar ruta <Icon name="arrow" size={15}/></button></article>)}</div></>}
    {section==='analytics' && <><OverviewTiles items={[{icon:'activity',value:'76.4%',label:'Participación',tone:'cyan'},{icon:'target',value:'72%',label:'Finalización',tone:'teal'},{icon:'chart',value:'18.4k',label:'Horas acumuladas',tone:'violet'}]}/><div className="dashboard-main-grid"><Panel title="Progreso de aprendizaje" eyebrow="TENDENCIAS · DEMO" action={<Demo compact/>}><div className="legend-row"><span><i className="dot blue"/> Participación</span><span><i className="dot violet"/> Finalización</span></div><TrendChart period="30 días"/></Panel><Panel title="Estado de finalización" eyebrow="MATRÍCULAS · DEMO"><CompletionDonut/></Panel></div><Panel title="Lectura responsable de datos" eyebrow="TRANSPARENCIA"><div className="info-callout"><Icon name="shield" size={22}/><p>Los valores de esta pantalla son ilustrativos. La versión conectada mostrará institución, periodo, origen y fecha de actualización de cada indicador.</p></div></Panel></>}
    {section==='skills' && <div className="dashboard-main-grid"><Panel title="Mapa de competencias" eyebrow="DOMINIO ESTIMADO · DEMO"><SkillRows/></Panel><Panel title="Niveles de dominio" eyebrow="REFERENCIA VISUAL"><div className="level-list">{['Principiante','Elemental','Intermedio','Avanzado','Experto'].map((x,i)=><div key={x}><span className={`level-bar level-${i}`}/><span>{x}</span><strong>0{i+1}</strong></div>)}</div><p className="muted-note">El dominio estimado por IA y el validado por un docente son resultados distintos.</p></Panel></div>}
    {section==='neural' && <><div className="neural-full panel"><div className="panel-head"><div><span className="panel-eyebrow">VISUALIZACIÓN INTERACTIVA</span><h2>Flujo de la red neuronal</h2></div><Demo compact/></div><NeuralNetwork running={running}/><div className="neural-controls"><div className="neural-state"><i className={`dot ${running?'cyan':'muted'}`}/>{running?'Demostración visual en movimiento':'Demostración en pausa'}</div><div><button className="outline-button" onClick={onToggle}><Icon name={running?'pause':'play'} size={16}/>{running?'Pausar':'Reanudar'}</button><button className="outline-button" onClick={()=>{onToggle();onDemo('Reiniciar animación')}}><Icon name="reset" size={16}/> Reiniciar</button></div></div></div><div className="mini-kpi-grid"><div className="mini-kpi"><span className="mini-kpi-icon tone-cyan"><Icon name="layers"/></span><strong>04</strong><small>Capas ilustrativas</small></div><div className="mini-kpi"><span className="mini-kpi-icon tone-violet"><Icon name="network"/></span><strong>16</strong><small>Nodos visualizados</small></div><div className="mini-kpi"><span className="mini-kpi-icon tone-teal"><Icon name="shield"/></span><strong>DEMO</strong><small>Sin modelo conectado</small></div></div><div className="info-callout"><Icon name="shield" size={22}/><p>Esta animación es una demostración de interfaz. Cuando exista un modelo entrenado, la topología, las métricas y los estados se recibirán del backend. No representa un entrenamiento activo.</p></div></>}
    {section==='tutor' && <div className="tutor-layout"><div className="panel tutor-chat"><div className="panel-head"><div><span className="panel-eyebrow">ACOMPAÑAMIENTO PERSONALIZADO</span><h2>Conversación de muestra</h2></div><Demo compact/></div><div className="chat-thread"><div className="chat-bubble bot"><div className="bubble-avatar"><Icon name="spark" size={18}/></div><div><small>EDUMASTER IA</small><p>¡Hola! Soy tu guía de aprendizaje. Puedo ayudarte a explorar rutas y detectar temas que conviene reforzar.</p></div></div><div className="chat-bubble human"><p>¿Qué puedo estudiar después de Fundamentos de IA?</p></div><div className="chat-bubble bot"><div className="bubble-avatar"><Icon name="spark" size={18}/></div><div><small>SUGERENCIA DE EJEMPLO</small><p>Podrías continuar con <strong>Redes neuronales aplicadas</strong>. Refuerza conceptos de modelos y evaluación; un docente podrá revisar la recomendación.</p></div></div></div><div className="chat-input"><input placeholder="La conversación se habilitará al conectar la API" disabled aria-label="Entrada del tutor no disponible"/><button onClick={()=>onDemo('Enviar mensaje')} disabled><Icon name="arrow" size={17}/></button></div></div><Panel title="Tu próximo paso" eyebrow="PROPUESTA · DEMO"><div className="suggestion-large"><span><Icon name="spark" size={28}/></span><h3>Aprende a tu ritmo</h3><p>Las recomendaciones reales incluirán su motivo, evidencia y versión del modelo utilizado.</p><button className="text-link" onClick={()=>onNavigate('recommendations')}>Ver recomendaciones <Icon name="arrow" size={15}/></button></div></Panel></div>}
    {section==='recommendations' && <><OverviewTiles items={[{icon:'spark',value:'08',label:'Sugerencias nuevas',tone:'violet'},{icon:'check',value:'14',label:'Aceptadas',tone:'teal'},{icon:'target',value:'76%',label:'Utilidad de ejemplo',tone:'cyan'}]}/><div className="recommendation-list">{[{title:'Profundiza en análisis de datos',why:'Relacionada con la ruta Ciencia de Datos',tone:'cyan',tag:'RECURSO'},{title:'Practica fundamentos de redes neuronales',why:'Refuerzo sugerido después del módulo de IA',tone:'violet',tag:'ACTIVIDAD'},{title:'Explora visualización de información',why:'Complementa tu progreso en diseño digital',tone:'teal',tag:'RUTA'}].map(r=><div className="recommendation-card" key={r.title}><span className={`reco-icon tone-${r.tone}`}><Icon name="spark" size={22}/></span><div><small>{r.tag} · DEMO</small><h3>{r.title}</h3><p>{r.why}</p></div><div className="reco-actions"><button className="outline-button" onClick={()=>onDemo('Descartar recomendación')}>Descartar</button><button className="primary-button" onClick={()=>onDemo('Aceptar recomendación')}>Explorar <Icon name="arrow" size={15}/></button></div></div>)}</div></>}
    {section==='assessments' && <><OverviewTiles items={[{icon:'check',value:'24',label:'Evaluaciones',tone:'teal'},{icon:'clock',value:'08',label:'En progreso',tone:'cyan'},{icon:'target',value:'81%',label:'Resultado promedio',tone:'violet'}]}/><Panel title="Evaluaciones recientes" eyebrow="EJEMPLOS DE INTERFAZ" action={<button className="primary-button" onClick={()=>onDemo('Crear evaluación')}>+ Nueva evaluación</button>}><div className="table-wrap"><table><thead><tr><th>Evaluación</th><th>Curso</th><th>Tipo</th><th>Estado</th><th>Intentos</th></tr></thead><tbody>{[['Introducción a modelos','Fundamentos de IA','Cuestionario','Publicada','184'],['Exploración de datos','Análisis con Python','Práctica','En revisión','92'],['Principios visuales','Diseño digital','Actividad','Borrador','—'],['Capas y activaciones','Redes neuronales','Cuestionario','Publicada','74']].map(r=><tr key={r[0]}>{r.map((cell,i)=><td key={i}>{i===3?<span className={`status-pill ${cell==='Publicada'?'good':cell==='Borrador'?'quiet':'pending'}`}>{cell}</span>:cell}</td>)}</tr>)}</tbody></table></div></Panel></>}
    {section==='certificates' && <><OverviewTiles items={[{icon:'award',value:'1,203',label:'Certificados emitidos',tone:'violet'},{icon:'check',value:'946',label:'Verificaciones',tone:'teal'},{icon:'clock',value:'18',label:'Pendientes',tone:'cyan'}]}/><Panel title="Credencial de muestra" eyebrow="CERTIFICACIÓN DIGITAL"><div className="certificate-preview"><div className="cert-decoration">✦</div><span>EDUMASTER.AI · CERTIFICACIÓN</span><h3>Certificado de logro</h3><p>Esta vista representa una credencial ilustrativa de finalización de curso.</p><strong>FOLIO DEMO-2026-001</strong><div className="cert-seal"><Icon name="award" size={30}/></div></div><p className="muted-note">La emisión real verificará requisitos académicos, folio único y código público.</p></Panel></>}
    {section==='community' && <><div className="community-grid"><Panel title="Conversaciones del curso" eyebrow="COMUNIDAD · DEMO" action={<button className="primary-button" onClick={()=>onDemo('Publicar conversación')}>+ Nueva publicación</button>}><div className="forum-list">{[{initial:'M',name:'María R.',title:'¿Cómo interpretar una matriz de confusión?',meta:'Fundamentos de IA · 6 respuestas',tone:'violet'},{initial:'J',name:'Jorge M.',title:'Recursos para practicar con Python',meta:'Análisis de datos · 12 respuestas',tone:'cyan'},{initial:'A',name:'Andrea L.',title:'Compartamos ejemplos de diseño accesible',meta:'Diseño digital · 4 respuestas',tone:'teal'}].map(f=><div className="forum-row" key={f.title}><span className={`avatar tone-${f.tone}`}>{f.initial}</span><div><small>{f.name}</small><h3>{f.title}</h3><p>{f.meta}</p></div><TinyArrow/></div>)}</div></Panel><Panel title="Normas de la comunidad" eyebrow="ESPACIO SEGURO"><div className="info-stack"><p><Icon name="shield"/> Respeta a los participantes y sus ideas.</p><p><Icon name="message"/> Publica preguntas dentro del curso correspondiente.</p><p><Icon name="users"/> La moderación y los permisos se conectarán al backend.</p></div></Panel></div></>}
    {section==='activity' && <div className="dashboard-main-grid"><Panel title="Línea de actividad" eyebrow="EVENTOS RECIENTES · DEMO"><div className="activity-list activity-list--large">{activities.concat(activities.slice(0,2)).map((a,i)=><div className="activity-row" key={`${a.title}-${i}`}><span className={`activity-icon tone-${a.tone}`}><Icon name={a.icon} size={17}/></span><div><strong>{a.title}</strong><span>{a.detail}</span></div><time>{a.time}</time></div>)}</div></Panel><Panel title="Centro de notificaciones" eyebrow="ESTADO DEL SISTEMA"><div className="empty-state"><span className="empty-glow"><Icon name="bell" size={30}/></span><h3>Todo al día</h3><p>Las notificaciones en tiempo real aparecerán aquí cuando el backend esté conectado.</p></div></Panel></div>}
    {section==='admin' && <><OverviewTiles items={[{icon:'users',value:'08',label:'Roles definidos',tone:'blue'},{icon:'shield',value:'01',label:'Institución DEMO',tone:'teal'},{icon:'activity',value:'24/7',label:'Visibilidad prevista',tone:'violet'}]}/><div className="dashboard-main-grid"><Panel title="Roles y acceso" eyebrow="PERMISOS PREVISTOS"><div className="role-list">{['Superadministrador','Administrador institucional','Director / coordinador','Docente / instructor','Estudiante','Analista de datos','ML Engineer','Auditor'].map((r,i)=><div key={r}><span className="role-number">0{i+1}</span><span>{r}</span><span className="status-pill quiet">Vista DEMO</span></div>)}</div></Panel><Panel title="Gobierno de datos" eyebrow="SEGURIDAD"><div className="info-stack"><p><Icon name="shield"/> La autorización real se aplicará en FastAPI.</p><p><Icon name="users"/> Cada usuario verá únicamente los datos permitidos.</p><p><Icon name="activity"/> Cambios sensibles y exportaciones quedarán auditados.</p></div></Panel></div></>}
  </div>;
}

function LoginScreen({ onLogin, theme, onThemeChange }: {
  onLogin: (email: string, password: string) => Promise<void>;
  theme: 'dark' | 'light';
  onThemeChange: () => void;
}) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try { await onLogin(email, password); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo iniciar sesión.'); }
    finally { setSubmitting(false); }
  };
  return <main className={`login-page theme-${theme}`}>
    <div className="login-ambient login-ambient--one"/><div className="login-ambient login-ambient--two"/>
    <div className="login-grid" aria-hidden="true"/>
    <div className="login-frame">
      <header className="login-header">
        <div className="login-brand"><span className="brand-mark"><span>e</span><i/></span><span className="brand-word"><strong>edumaster<span>.ai</span></strong><small>INTELLIGENT LEARNING</small></span></div>
        <button className="login-theme" onClick={onThemeChange} aria-label={theme === 'dark' ? 'Activar modo claro' : 'Activar modo oscuro'} title={theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}><Icon name={theme === 'dark' ? 'sun' : 'moon'} size={19}/><span>{theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}</span></button>
      </header>
      <div className="login-layout">
        <section className="login-visual" aria-label="Presentación de EduMaster">
          <span className="login-eyebrow"><span/> PLATAFORMA EDUCATIVA INTELIGENTE</span>
          <h1>El futuro del aprendizaje <em>comienza aquí.</em></h1>
          <p>Explora rutas, comprende el progreso y descubre una nueva forma de aprender en un solo lugar.</p>
          <div className="login-network" aria-hidden="true">
            <div className="login-orbit login-orbit--outer"/><div className="login-orbit login-orbit--inner"/>
            <svg viewBox="0 0 600 460" preserveAspectRatio="xMidYMid meet">
              <defs><linearGradient id="login-line" x1="0" x2="1" y1="0" y2="1"><stop stopColor="#15dbfc" stopOpacity=".55"/><stop offset="1" stopColor="#9978ff" stopOpacity=".42"/></linearGradient><radialGradient id="login-core"><stop stopColor="#50e5ff"/><stop offset=".5" stopColor="#128af1"/><stop offset="1" stopColor="#542fe6"/></radialGradient></defs>
              <g className="login-lines" fill="none" stroke="url(#login-line)" strokeWidth="1.15">
                <path d="M300 226 138 124 92 235 164 342 300 226 421 91 514 174 478 330 354 377 300 226M138 124 421 91 514 174 300 226 92 235 478 330 164 342 354 377 138 124M164 342 421 91M92 235 354 377"/>
              </g>
              {([[138,124],[92,235],[164,342],[421,91],[514,174],[478,330],[354,377]] as const).map(([x,y],i)=><g key={i} className="login-node" style={{animationDelay:`${i * -.42}s`}}><circle cx={x} cy={y} r="10" fill="#1479d7" fillOpacity=".16"/><circle cx={x} cy={y} r="3.5" fill={i%2 ? '#a18bff' : '#30dbf7'}/></g>)}
              <g className="login-core"><circle cx="300" cy="226" r="62" fill="url(#login-core)" opacity=".13"/><circle cx="300" cy="226" r="43" fill="url(#login-core)" opacity=".22"/><circle cx="300" cy="226" r="26" fill="url(#login-core)"/><circle cx="300" cy="226" r="7" fill="#d4faff"/></g>
            </svg>
            <div className="login-float login-float--one"><span><Icon name="spark" size={17}/></span><div><strong>Aprende</strong><small>A tu propio ritmo</small></div></div>
            <div className="login-float login-float--two"><span><Icon name="chart" size={17}/></span><div><strong>Progresa</strong><small>Con claridad</small></div></div>
          </div>
          <div className="login-visual-foot"><span><Icon name="shield" size={16}/> ESPACIO DE DEMOSTRACIÓN</span><span>APRENDE · PRACTICA · DESTACA</span></div>
        </section>
        <section className="login-panel" aria-labelledby="login-title">
          <div className="login-panel-top"><span className="login-access-icon"><Icon name="lock" size={23}/></span><span className="login-portal-label"><span/> ACCESO A LA PLATAFORMA</span></div>
          <h2 id="login-title">Bienvenido <span>de nuevo.</span></h2>
          <p className="login-subtitle">Inicia sesión para entrar a tu espacio de aprendizaje.</p>
          <form onSubmit={submit} className="login-form" noValidate>
            <label htmlFor="login-email">Correo electrónico</label>
            <div className={`login-field ${error ? 'login-field--error' : ''}`}><Icon name="mail" size={19}/><input id="login-email" type="email" autoComplete="username" inputMode="email" placeholder="nombre@correo.com" value={email} onChange={e => {setEmail(e.target.value);setError('');}} required/></div>
            <label htmlFor="login-password">Contraseña</label>
            <div className={`login-field ${error ? 'login-field--error' : ''}`}><Icon name="lock" size={19}/><input id="login-password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="Ingresa tu contraseña" value={password} onChange={e => {setPassword(e.target.value);setError('');}} required/><button type="button" onClick={() => setShowPassword(visible => !visible)} aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'} aria-pressed={showPassword}><Icon name={showPassword ? 'eyeOff' : 'eye'} size={19}/></button></div>
            {error && <div className="login-error" role="alert"><Icon name="shield" size={16}/>{error}</div>}
            <button type="submit" className="login-submit" disabled={submitting || !isConfigured}>{submitting ? 'Verificando acceso…' : 'Entrar a EduMaster'} <Icon name="arrow" size={19}/></button>
          </form>
          <div className="login-support"><span><Icon name="shield" size={17}/> Acceso protegido con Supabase</span><p>{isConfigured ? 'Tu identidad y tus permisos se verifican antes de acceder.' : 'Configura las variables del proyecto y la API para habilitar el acceso.'}</p></div>
        </section>
      </div>
      <footer className="login-footer"><span>© {new Date().getFullYear()} EduMaster.ai</span><span>Diseñado para aprender sin límites</span></footer>
    </div>
  </main>;
}

export default function App() {
  const [authState, setAuthState] = useState<'loading' | 'signedIn' | 'signedOut'>('loading');
  const [profile, setProfile] = useState<Profile | null>(null);
  const dashboardState = useDashboard(profile);
  const [section, setSection] = useState('dashboard');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    try { return localStorage.getItem('edumaster-theme') === 'light' ? 'light' : 'dark'; }
    catch { return 'dark'; }
  });
  const [running, setRunning] = useState(true);
  const [period, setPeriod] = useState('30 días');
  const [globalSearch, setGlobalSearch] = useState('');
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  useEffect(() => {
    document.documentElement.dataset.edumasterTheme = theme;
    try { localStorage.setItem('edumaster-theme', theme); } catch { /* La interfaz sigue funcionando sin almacenamiento local. */ }
  }, [theme]);
  useEffect(() => {
    let mounted = true;
    if (!supabase || !isConfigured) { setAuthState('signedOut'); return; }
    const client = supabase;
    const { data: { subscription } } = client.auth.onAuthStateChange((event) => {
      if (event === 'SIGNED_OUT' && mounted) { setProfile(null); setAuthState('signedOut'); }
    });
    void client.auth.getSession().then(async ({ data: { session } }) => {
      if (!session) { if (mounted) setAuthState('signedOut'); return; }
      try {
        const current = await loadProfile(session.access_token);
        if (mounted) { setProfile(current); setAuthState('signedIn'); }
      } catch {
        await client.auth.signOut({ scope: 'local' });
        if (mounted) setAuthState('signedOut');
      }
    }).catch(() => { if (mounted) setAuthState('signedOut'); });
    return () => { mounted = false; subscription.unsubscribe(); };
  }, []);
  const page = PAGE[section] ?? PAGE.dashboard;
  const navigate = (id:string) => {setSection(id);setMobileOpen(false);setSearchOpen(false);setNotificationOpen(false);setProfileOpen(false);window.scrollTo({top:0,behavior:'smooth'});};
  const toggleSidebar = () => {
    if (window.matchMedia('(max-width: 780px)').matches) setMobileOpen(open => !open);
    else setSidebarCollapsed(collapsed => !collapsed);
  };
  const visibleNavigation = useMemo(() => navigation.filter(n => n.id !== 'admin' || profile?.role === 'superadmin' || profile?.role === 'admin'), [profile?.role]);
  const searchResults = useMemo(()=>visibleNavigation.filter(n=>n.label.toLowerCase().includes(globalSearch.toLowerCase())),[globalSearch,visibleNavigation]);
  const menuExpanded = window.matchMedia('(max-width: 780px)').matches ? mobileOpen : !sidebarCollapsed;
  const date = new Intl.DateTimeFormat('es-PE',{day:'numeric',month:'long',year:'numeric',timeZone:'America/Lima'}).format(new Date());
  const login = async (email: string, password: string) => {
    if (!supabase || !isConfigured) throw new Error('Configura Supabase y la API antes de iniciar sesión.');
    const { data, error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (error || !data.session) throw error instanceof Error ? error : new Error('No se pudo iniciar sesión.');
    try {
      const current = await loadProfile(data.session.access_token);
      setProfile(current);
      setAuthState('signedIn');
    } catch (cause) {
      await supabase.auth.signOut({ scope: 'local' });
      throw cause;
    }
    setSection('dashboard');
  };
  const logout = async () => {
    if (supabase) {
      const { error } = await supabase.auth.signOut({ scope: 'local' });
      if (error) { window.alert('No se pudo cerrar la sesión. Vuelve a intentarlo.'); return; }
    }
    setProfile(null);
    setAuthState('signedOut');
    setSection('dashboard');
    setProfileOpen(false);
    setNotificationOpen(false);
    setSearchOpen(false);
    setMobileOpen(false);
    setGlobalSearch('');
    window.scrollTo({top:0,behavior:'instant'});
  };
  if (authState === 'loading') return <div className={`auth-loading theme-${theme}`} role="status">Verificando sesión…</div>;
  if (authState !== 'signedIn' || !profile) return <LoginScreen onLogin={login} theme={theme} onThemeChange={()=>setTheme(current=>current==='dark'?'light':'dark')}/>;
  return <div className={`app-shell theme-${theme} ${sidebarCollapsed ? 'app-shell--sidebar-collapsed' : ''}`}>
    {mobileOpen && <button className="mobile-overlay" aria-label="Cerrar menú" onClick={()=>setMobileOpen(false)}/>}
    <aside id="edumaster-sidebar" className={`sidebar ${mobileOpen?'sidebar--open':''} ${sidebarCollapsed?'sidebar--collapsed':''}`}><div className="brand"><div className="brand-mark"><span>e</span><i/></div><div className="brand-word"><strong>edumaster<span>.ai</span></strong><small>INTELLIGENT LEARNING</small></div><button className="mobile-close" onClick={()=>setMobileOpen(false)} aria-label="Cerrar menú"><Icon name="close"/></button></div>
      <div className="workspace-card"><span className="workspace-avatar">E</span><div><small>ESPACIO DE TRABAJO</small><strong>EduMaster Demo</strong></div><Icon name="chevron" size={15}/></div>
      <nav className="sidebar-nav" aria-label="Navegación principal">{(['principal','academico','inteligencia','sistema'] as const).map(g=><div className="nav-group" key={g}><div className="nav-group-title">{g==='principal'?'GENERAL':g==='academico'?'ACADÉMICO':g==='inteligencia'?'INTELIGENCIA':'GESTIÓN'}</div>{visibleNavigation.filter(n=>n.group===g).map(n=><button key={n.id} className={`nav-link ${section===n.id?'nav-link--active':''}`} onClick={()=>navigate(n.id)} aria-current={section===n.id?'page':undefined}><Icon name={n.icon} size={18}/><span>{n.label}</span>{n.id==='tutor'&&<i className="nav-new">AI</i>}</button>)}</div>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-upgrade"><span className="upgrade-star"><Icon name="spark" size={17}/></span><strong>Aprende sin límites</strong><p>Una experiencia diseñada para descubrir tu potencial.</p><span className="upgrade-lines"/></div><div className="sidebar-profile"><span className="profile-avatar">EM</span><div><strong>{profile.email}</strong><small>{profile.role} · {profile.institution_id ? 'Institución asignada' : 'Sin institución'}</small></div><Icon name="more" size={17}/></div></div>
    </aside>
    <div className="main-column"><header className="topbar"><div className="topbar-left">
      <button className="sidebar-toggle icon-button" onClick={toggleSidebar} aria-controls="edumaster-sidebar" aria-label={menuExpanded ? 'Ocultar menú lateral' : 'Mostrar menú lateral'} aria-expanded={menuExpanded} title="Mostrar u ocultar menú"><Icon name="menu" size={20}/></button>
      <div className="breadcrumbs"><span>EduMaster</span><span className="slash">/</span><strong>{page.title}</strong></div></div>
      <div className="topbar-right"><span className="live-indicator"><i/> {dashboardState.connected ? 'Datos en vivo' : 'Datos académicos'}</span><div className="topbar-divider"/>
      <div className="header-search"><Icon name="search" size={17}/><input aria-label="Buscar sección" placeholder="Buscar en la plataforma..." value={globalSearch} onFocus={()=>setSearchOpen(true)} onChange={e=>{setGlobalSearch(e.target.value);setSearchOpen(true)}}/><kbd>⌘ K</kbd>{searchOpen&&globalSearch&&<div className="search-popover">{searchResults.length?searchResults.map(n=><button key={n.id} onClick={()=>{navigate(n.id);setGlobalSearch('')}}><Icon name={n.icon} size={17}/>{n.label}</button>):<p>Sin secciones coincidentes</p>}</div>}</div>
      <button className="header-icon theme-toggle" onClick={()=>setTheme(current=>current==='dark'?'light':'dark')} aria-label={theme==='dark'?'Activar modo claro':'Activar modo oscuro'} aria-pressed={theme==='light'} title={theme==='dark'?'Cambiar a modo claro':'Cambiar a modo oscuro'}><Icon name={theme==='dark'?'sun':'moon'} size={19}/></button>
      <div className="popover-anchor"><button className="header-icon" aria-label="Notificaciones" onClick={()=>{setNotificationOpen(!notificationOpen);setProfileOpen(false)}}><Icon name="bell" size={19}/><i/></button>{notificationOpen&&<div className="header-popover"><strong>Notificaciones académicas</strong>{dashboardState.data?.recent_events.length ? dashboardState.data.recent_events.slice(0,4).map(event=><p key={event.id}>{event.title} · {new Intl.DateTimeFormat('es-PE',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'America/Lima'}).format(new Date(event.occurred_at))}</p>) : <p>No hay actividad nueva en este periodo.</p>}<button onClick={()=>navigate('activity')}>Ir a actividad <Icon name="arrow" size={14}/></button></div>}</div>
      <div className="popover-anchor"><button className="top-avatar" aria-label="Abrir perfil" aria-expanded={profileOpen} onClick={()=>{setProfileOpen(!profileOpen);setNotificationOpen(false)}}>EM</button>{profileOpen&&<div className="header-popover profile-popover"><strong>{profile.email}</strong><p>Rol: {profile.role}</p><span>Acceso verificado por Supabase y la API.</span><div className="profile-popover-divider"/><button className="logout-button" onClick={()=>void logout()}><Icon name="logout" size={16}/> Cerrar sesión <Icon name="arrow" size={15}/></button></div>}</div></div></header>
      <main className="content"><div className="page-heading"><div><span className="page-eyebrow"><span/> {page.eyebrow}</span><h1>{page.title}<span className="heading-period">.</span></h1><p>{page.desc}</p></div><div className="heading-actions">{!['dashboard','analytics','activity','courses','paths','assessments'].includes(section) && <Demo/>}<div className="date-pill"><Icon name="calendar" size={16}/>{date}</div></div></div>{section==='dashboard'||section==='analytics'?<LiveDashboard state={dashboardState} onNavigate={navigate}/>:section==='activity'?<LiveActivity state={dashboardState}/>:section==='courses'||section==='paths'||section==='assessments'?<AcademicPage key={section} section={section} profile={profile}/>:<SecondaryPage key={section} section={section} onNavigate={navigate} running={running} onToggle={()=>setRunning(!running)}/>}<footer className="footer"><span>© {new Date().getFullYear()} EduMaster.ai · Aprende · Practica · Destaca</span><span>Datos académicos desde la API · Inteligencia artificial ilustrativa</span></footer></main>
    </div>
  </div>;
}

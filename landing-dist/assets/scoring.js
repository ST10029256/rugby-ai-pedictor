/* Rugby union scoring guide. Local examples only; no match data or persistence. */
(() => {
  'use strict';
  const types = Object.freeze({
    try: { points: 5, label: 'Try' }, conversion: { points: 2, label: 'Conversion' },
    penalty: { points: 3, label: 'Penalty goal' }, drop: { points: 3, label: 'Drop goal' },
    penaltyTry: { points: 7, label: 'Penalty try' }
  });
  const initial = () => ({ home: 0, away: 0, pending: null, events: [] });
  function addScore(state, team, type) {
    if (!['home', 'away'].includes(team) || !types[type]) return state;
    if (type === 'conversion' && state.pending !== team) return state;
    return { ...state, [team]: state[team] + types[type].points,
      pending: type === 'try' ? team : null,
      events: [...state.events, { team, type }] };
  }
  function undo(state) {
    return state.events.slice(0, -1).reduce((next, event) => addScore(next, event.team, event.type), initial());
  }
  if (typeof module !== 'undefined' && module.exports) { module.exports = { initial, addScore, undo }; return; }
  const $ = (id) => document.getElementById(id);
  if (!$('scoreHome')) return;
  let state = initial();
  let team = 'home';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const teamButtons = [...document.querySelectorAll('[data-score-team]')];
  const actions = [...document.querySelectorAll('[data-score-action]')];
  document.querySelector('.score-interactions').hidden = false;
  function render(message, animateTeam) {
    document.querySelector('.score-console').classList.toggle('is-large', Math.max(state.home, state.away) >= 100);
    $('scoreHome').textContent = String(state.home).padStart(2, '0');
    $('scoreAway').textContent = String(state.away).padStart(2, '0');
    $('scoreMessage').textContent = message;
    $('scoreEventCount').textContent = `${state.events.length} scoring action${state.events.length === 1 ? '' : 's'}`;
    teamButtons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.scoreTeam === team)));
    actions.find((button) => button.dataset.scoreAction === 'conversion').disabled = state.pending !== team;
    $('conversionHelp').textContent = state.pending
      ? `${state.pending === 'home' ? 'Home' : 'Away'} scored the try. Add their conversion, or continue with another score.`
      : 'A conversion is available to the side that just scored a try.';
    $('scoreUndo').disabled = $('scoreReset').disabled = !state.events.length;
    if (animateTeam && window.gsap && !reduced.matches) {
      const target = $(animateTeam === 'home' ? 'scoreHome' : 'scoreAway');
      window.gsap.fromTo(target, { y: -12, opacity: .25, scale: 1.06 }, { y: 0, opacity: 1, scale: 1, duration: .42, ease: 'power3.out', overwrite: true, clearProps: 'opacity,transform' });
    }
  }
  const scoreText = () => `Home ${state.home}, away ${state.away}.`;
  teamButtons.forEach((button) => button.addEventListener('click', () => {
    team = button.dataset.scoreTeam;
    render(`${team === 'home' ? 'Home' : 'Away'} selected. ${scoreText()}`);
  }));
  actions.forEach((button) => button.addEventListener('click', () => {
    const type = button.dataset.scoreAction;
    const next = addScore(state, team, type);
    if (next === state) return;
    state = next;
    render(`${types[type].label} for ${team}: +${types[type].points}. ${scoreText()}`, team);
  }));
  $('scoreUndo').addEventListener('click', () => { state = undo(state); render(`Last action undone. ${scoreText()}`); });
  $('scoreReset').addEventListener('click', () => { state = initial(); render('Score reset. Choose a side, then add a score.'); });
})();

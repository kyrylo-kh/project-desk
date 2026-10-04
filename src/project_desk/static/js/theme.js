// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* Project Desk: the theme, set before the first paint (a classic script in <head>, so a dark theme
   never flashes light). It reads only the viewer's own saved choice; main.js applies the config's
   default when there is none, and runs the theme switcher. "auto" means no data-theme attribute:
   the stylesheet then follows the OS. */
(function () {
  var THEMES = ['light', 'dark', 'contrast', 'manila', 'terminal'];
  try {
    var saved = JSON.parse(localStorage.getItem('project-desk:theme') || 'null');
    if (THEMES.indexOf(saved) >= 0) document.documentElement.setAttribute('data-theme', saved);
  } catch (e) {
    /* storage blocked or a bad value: the OS decides */
  }
})();

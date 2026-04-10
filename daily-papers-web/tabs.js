/* === Tab switching for detail pages === */
function switchTab(tabId, containerId) {
  var root = containerId ? document.getElementById(containerId) : document;
  root.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
  root.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
  var panel = root.querySelector('#panel-'+tabId) || root.querySelector('[id$="panel-'+tabId+'"]');
  if(panel) panel.classList.add('active');
  root.querySelectorAll('.tab-btn').forEach(function(b){
    if(b.getAttribute('data-tab')===tabId) b.classList.add('active');
  });
  history.replaceState(null,'','#'+tabId);
}
document.addEventListener('DOMContentLoaded', function() {
  var hash = location.hash.slice(1);
  var target = hash && document.querySelector('[data-tab="'+hash+'"]');
  if (target) switchTab(hash);
  // Re-render KaTeX inside <details> when opened
  document.querySelectorAll('details.paper-note').forEach(function(d) {
    d.addEventListener('toggle', function() {
      if (d.open && typeof renderMathInElement === 'function') {
        renderMathInElement(d, {delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}]});
      }
    });
  });
});

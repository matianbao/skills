/* === Roundtable Dashboard === */
document.addEventListener('DOMContentLoaded', function() {
  // Add hover effects to meeting cards
  document.querySelectorAll('.meeting-card').forEach(function(card) {
    card.addEventListener('mouseenter', function() {
      this.style.borderColor = 'var(--accent)';
    });
    card.addEventListener('mouseleave', function() {
      this.style.borderColor = 'var(--border)';
    });
  });

  // Assign colors to speaker blocks on detail pages
  var speakers = {};
  var colorIdx = 0;
  var colors = ['var(--accent)', 'var(--fire)', 'var(--green)', 'var(--yellow)',
                'var(--purple)', 'var(--pink)', 'var(--orange)', '#79c0ff'];

  document.querySelectorAll('.speaker-block').forEach(function(block) {
    var name = block.dataset.speaker;
    if (name && !speakers[name]) {
      speakers[name] = colors[colorIdx % colors.length];
      colorIdx++;
    }
    if (name && speakers[name]) {
      block.style.borderLeftColor = speakers[name];
    }
  });
});

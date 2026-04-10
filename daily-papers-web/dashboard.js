/* === Dashboard (index page) === */
var curYear, curMonth;
function pad(n){ return n<10?'0'+n:''+n; }

function renderCalendar(y,m){
  curYear=y; curMonth=m;
  var el=document.getElementById('cal-grid');
  document.getElementById('cal-month').textContent=y+'-'+pad(m);
  var first=new Date(y,m-1,1), last=new Date(y,m,0);
  var startDow=(first.getDay()+6)%7;
  var html='';
  var dateSet={};
  DAYS_DATA.forEach(function(d){ dateSet[d.date]=d; });
  for(var i=0;i<startDow;i++) html+='<div class="cal-day"></div>';
  for(var d=1;d<=last.getDate();d++){
    var ds=y+'-'+pad(m)+'-'+pad(d);
    var day=dateSet[ds];
    var cls='cal-day';
    if(day) cls+=' has-data';
    var mc=document.getElementById('main-content');
    if(mc && mc.dataset.date===ds) cls+=' selected';
    var dot='';
    if(day && day.counts.must>0) dot='<span class="cal-dot fire"></span>';
    else if(day && day.counts.look>0) dot='<span class="cal-dot look"></span>';
    var click=day?'onclick="selectDate(\''+ds+'\')"':'';
    html+='<div class="'+cls+'" '+click+'>'+d+dot+'</div>';
  }
  el.innerHTML=html;
}
function prevMonth(){ curMonth--; if(curMonth<1){curMonth=12;curYear--;} renderCalendar(curYear,curMonth); }
function nextMonth(){ curMonth++; if(curMonth>12){curMonth=1;curYear++;} renderCalendar(curYear,curMonth); }

/* --- Lazy-load detail content via fetch --- */
var contentCache = {};

function selectDate(ds){
  var mc=document.getElementById('main-content');
  mc.dataset.date=ds;
  // Clear topic filter
  activeTopic=null;
  document.querySelectorAll('.trend-row').forEach(function(r){
    r.classList.remove('active-topic','dimmed');
  });
  // Update calendar selection
  var parts=ds.split('-');
  var sy=parseInt(parts[0]),sm=parseInt(parts[1]);
  if(sy!==curYear||sm!==curMonth) renderCalendar(sy,sm);
  else{
    document.querySelectorAll('.cal-day').forEach(function(d){d.classList.remove('selected');});
    document.querySelectorAll('.cal-day.has-data').forEach(function(d){
      if(d.textContent.trim()===''+parseInt(parts[2])) d.classList.add('selected');
    });
  }
  // Update quality timeline selection
  document.querySelectorAll('.qt-row').forEach(function(r){
    r.classList.toggle('selected',r.dataset.date===ds);
  });
  history.replaceState(null,'','#'+ds);

  // Find day metadata
  var day=null;
  DAYS_DATA.forEach(function(d){ if(d.date===ds) day=d; });
  if(!day){ mc.innerHTML='<div class="no-data">该日期无推荐数据</div>'; return; }

  // Check cache first
  if(contentCache[ds]){
    _renderDayContent(mc, ds, day, contentCache[ds]);
    return;
  }
  // Fetch the fragment file
  mc.innerHTML='<div class="loading">加载中</div>';
  fetch('fragments/'+ds+'.html')
    .then(function(r){ return r.ok ? r.text() : Promise.reject('not found'); })
    .then(function(html){
      contentCache[ds]=html;
      // Only render if still on this date
      if(mc.dataset.date===ds) _renderDayContent(mc, ds, day, html);
    })
    .catch(function(){
      // Fallback: try full detail page
      mc.innerHTML='<div class="day-hero"><h2>'+ds+' '+day.weekday+'</h2></div>'
        +'<p><a href="'+ds+'.html" class="view-detail">查看完整页面 →</a></p>';
    });
}

function _renderDayContent(mc, ds, day, html){
  mc.innerHTML='<div class="day-hero"><h2>'+ds+' '+day.weekday+'</h2></div>'+html;
  // Activate default "all" tab
  var allPanel=mc.querySelector('[id$="panel-all"]');
  if(allPanel) allPanel.classList.add('active');
  var allBtn=mc.querySelector('.tab-btn[data-tab="all"]');
  if(allBtn) allBtn.classList.add('active');
  // Re-render KaTeX
  if(typeof renderMathInElement==='function'){
    renderMathInElement(mc,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}]});
  }
}

/* --- Tab switching (unified) --- */
function switchTab(tabId, container){
  var root = container ? document.getElementById(container) : document;
  root.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
  root.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
  // Find panel - try exact id first, then suffix match
  var panel = root.querySelector('#panel-'+tabId) || root.querySelector('[id$="panel-'+tabId+'"]');
  if(panel) panel.classList.add('active');
  root.querySelectorAll('.tab-btn').forEach(function(b){
    if(b.getAttribute('data-tab')===tabId) b.classList.add('active');
  });
}

/* --- Topic filtering --- */
var activeTopic=null;
var savedDateBeforeTopic=null;

function renderTrends(){
  var agg={};
  DAYS_DATA.forEach(function(d){
    if(!d.topicCounts) return;
    Object.keys(d.topicCounts).forEach(function(k){
      agg[k]=(agg[k]||0)+d.topicCounts[k];
    });
  });
  var sorted=Object.entries(agg).sort(function(a,b){return b[1]-a[1];}).slice(0,8);
  var max=sorted.length?sorted[0][1]:1;
  var el=document.getElementById('topic-trends');
  var html='';
  sorted.forEach(function(e){
    var pct=Math.round(e[1]/max*100);
    html+='<div class="trend-row" data-topic="'+e[0]+'" onclick="filterByTopic(\''+e[0].replace(/'/g,"\\'")+'\')">'
      +'<span class="trend-label" data-full="'+e[0]+'" title="'+e[0]+'">'+e[0]+'</span>'
      +'<div class="trend-bar-bg"><div class="trend-bar accent" style="width:'+pct+'%"></div></div>'
      +'<span class="trend-count">'+e[1]+'</span></div>';
  });
  el.innerHTML=html;
}

function filterByTopic(topic){
  var mc=document.getElementById('main-content');
  if(activeTopic===topic){ clearTopicFilter(); return; }
  if(!activeTopic && mc.dataset.date) savedDateBeforeTopic=mc.dataset.date;
  activeTopic=topic;
  // Highlight active trend row
  document.querySelectorAll('.trend-row').forEach(function(r){
    r.classList.remove('active-topic','dimmed');
    if(r.dataset.topic===topic) r.classList.add('active-topic');
    else r.classList.add('dimmed');
  });
  // Deselect calendar & quality timeline
  document.querySelectorAll('.cal-day').forEach(function(d){d.classList.remove('selected');});
  document.querySelectorAll('.qt-row').forEach(function(r){r.classList.remove('selected');});

  // Collect papers matching this topic from all days (need to fetch fragments)
  mc.innerHTML='<div class="loading">加载主题数据</div>';
  var promises = DAYS_DATA.map(function(d){
    if(!d.topicCounts || !d.topicCounts[topic]) return Promise.resolve(null);
    if(contentCache[d.date]) return Promise.resolve({date:d.date, weekday:d.weekday, html:contentCache[d.date]});
    return fetch('fragments/'+d.date+'.html')
      .then(function(r){ return r.ok ? r.text() : ''; })
      .then(function(html){ contentCache[d.date]=html; return {date:d.date, weekday:d.weekday, html:html}; })
      .catch(function(){ return null; });
  });
  Promise.all(promises).then(function(results){
    if(activeTopic!==topic) return; // stale
    var totalCount=0;
    var bodyHtml='<div class="topic-page">';
    bodyHtml+='<div class="topic-filter-bar"><span>\ud83d\udd0d 主题: <strong>'+topic+'</strong></span>'
      +'<button class="clear-filter" onclick="clearTopicFilter()">\u2715 返回</button></div>';
    var globalIdx=0;
    results.forEach(function(r){
      if(!r || !r.html) return;
      // Parse cards with matching topic from the fragment
      var tmp=document.createElement('div');
      tmp.innerHTML=r.html;
      var cards=tmp.querySelectorAll('.paper-card[data-topic="'+topic+'"]');
      if(cards.length===0) return;
      totalCount+=cards.length;
      bodyHtml+='<div class="topic-date-group">';
      bodyHtml+='<h3 class="topic-date-header">\ud83d\udcc5 '+r.date+' '+r.weekday+'<span class="topic-date-count">'+cards.length+' 篇</span></h3>';
      cards.forEach(function(card){
        globalIdx++;
        var cardHtml=card.innerHTML.replace(/<h3([^>]*)>\s*\d+\.\s*/,'<h3$1>'+globalIdx+'. ');
        bodyHtml+='<div class="paper-card" data-topic="'+topic+'">'+cardHtml+'</div>';
      });
      bodyHtml+='</div>';
    });
    if(totalCount===0) bodyHtml+='<div class="no-data">该主题下暂无论文</div>';
    bodyHtml+='</div>';
    bodyHtml=bodyHtml.replace('<strong>'+topic+'</strong>',
      '<strong>'+topic+'</strong> <span class="topic-total">共 '+totalCount+' 篇</span>');
    mc.innerHTML=bodyHtml;
    mc.dataset.date='';
    if(typeof renderMathInElement==='function'){
      renderMathInElement(mc,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}]});
    }
    history.replaceState(null,'','#topic-'+encodeURIComponent(topic));
  });
}

function clearTopicFilter(){
  activeTopic=null;
  document.querySelectorAll('.trend-row').forEach(function(r){
    r.classList.remove('active-topic','dimmed');
  });
  if(savedDateBeforeTopic){ selectDate(savedDateBeforeTopic); savedDateBeforeTopic=null; }
  else if(DAYS_DATA.length>0){ selectDate(DAYS_DATA[0].date); }
}

/* --- Quality timeline --- */
function renderQuality(){
  var el=document.getElementById('quality-timeline');
  var html='';
  DAYS_DATA.forEach(function(d){
    var short=d.date.slice(5);
    var dots='';
    for(var i=0;i<d.counts.must;i++) dots+='<span class="qt-dot fire"></span>';
    for(var i=0;i<d.counts.look;i++) dots+='<span class="qt-dot look"></span>';
    for(var i=0;i<d.counts.skip;i++) dots+='<span class="qt-dot skip"></span>';
    html+='<div class="qt-row" data-date="'+d.date+'" onclick="selectDate(\''+d.date+'\')">'
      +'<span class="qt-date">'+short+'</span>'
      +'<div class="qt-dots">'+dots+'</div></div>';
  });
  el.innerHTML=html;
}

/* --- Init --- */
document.addEventListener('DOMContentLoaded',function(){
  renderTrends();
  renderQuality();
  var hash=location.hash.slice(1);
  if(hash.startsWith('topic-')){
    var topic=decodeURIComponent(hash.slice(6));
    var parts=DAYS_DATA[0].date.split('-');
    renderCalendar(parseInt(parts[0]),parseInt(parts[1]));
    savedDateBeforeTopic=DAYS_DATA[0].date;
    filterByTopic(topic);
  } else {
    var initDate=hash||DAYS_DATA[0].date;
    var parts=initDate.split('-');
    renderCalendar(parseInt(parts[0]),parseInt(parts[1]));
    selectDate(initDate);
  }
});

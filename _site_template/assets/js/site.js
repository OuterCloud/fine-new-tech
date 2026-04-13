/* ── Share ── */
function sharePost() {
  var url = window.location.href;
  var title = typeof POST_TITLE !== 'undefined' ? POST_TITLE : document.title;
  if (navigator.share) {
    navigator.share({ title: title, url: url }).catch(function () {});
  } else {
    navigator.clipboard.writeText(url).then(function () {
      showToast('链接已复制');
    }).catch(function () {
      prompt('复制链接：', url);
    });
  }
}

/* ── Toast ── */
function showToast(msg) {
  var t = document.createElement('div');
  t.className = 'fnt-toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function () { t.classList.add('show'); }, 10);
  setTimeout(function () {
    t.classList.remove('show');
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 300);
  }, 2500);
}

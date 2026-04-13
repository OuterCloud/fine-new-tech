---
layout: home
title: DailyPulse · 每日脉搏
---

> 聚合 **GitHub Trending**、**Hacker News**、**arXiv**、**Product Hunt** 与**财经要闻**，由 AI 每日生成中英双语简报。

---

## 最新报告 / Latest Reports

<ul>
  {% for post in site.posts limit:10 %}
  <li>
    <strong><a href="{{ post.url | relative_url }}">{{ post.title }}</a></strong>
    <span style="color:#888;font-size:0.9em;margin-left:8px;">{{ post.date | date: "%Y-%m-%d" }}</span>
    {% if post.excerpt %}
    <p style="margin:4px 0 0 0;color:#555;font-size:0.95em;">{{ post.excerpt | strip_html | truncatewords: 30 }}</p>
    {% endif %}
  </li>
  {% endfor %}
</ul>

{% if site.posts.size == 0 %}
*暂无报告。*
{% endif %}


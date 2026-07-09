---
tags:
  - dashboard
---

# 📊 Research Dashboard

> Dataview プラグインが有効なら自動で表になります（設定 → Community plugins → Dataview を Enable）。
> テーマごとに読む → [[🗂 論文ビュー（テーマ別）]]

---

## 🆕 最近追加された論文（新しい順・上位20）

```dataview
TABLE WITHOUT ID
  file.link AS "論文",
  read_date AS "追加日",
  filter(tags, (t) => t != "literature") AS "タグ",
  year AS "年"
FROM "literature_notes"
WHERE status = "read"
SORT read_date DESC
LIMIT 20
```

## 📚 状態と件数

```dataview
TABLE WITHOUT ID
  key AS "状態",
  length(rows) AS "本数"
FROM "literature_notes"
GROUP BY status
```

## 🏷️ テーマ別の本数（多い順）

```dataview
TABLE WITHOUT ID
  key AS "タグ",
  length(rows) AS "本数"
FROM "literature_notes"
FLATTEN tags AS tag
WHERE tag != "literature"
GROUP BY tag
SORT length(rows) DESC
```

## ⭐ 高評価の論文（rating 4以上）

```dataview
TABLE WITHOUT ID
  file.link AS "論文",
  filter(tags, (t) => t != "literature") AS "タグ",
  year AS "年",
  my_rating AS "評価"
FROM "literature_notes"
WHERE my_rating != null AND number(split(my_rating, "/")[0]) >= 4
SORT number(split(my_rating, "/")[0]) DESC, read_date DESC
```

## 📥 未読・読みかけ

```dataview
TABLE WITHOUT ID
  file.link AS "論文",
  status AS "状態",
  year AS "年"
FROM "literature_notes"
WHERE status != "read"
SORT year DESC
```

## 🧠 概念ノート（被リンクが多い順）

```dataview
TABLE WITHOUT ID
  file.link AS "概念",
  domain AS "領域",
  length(file.inlinks) AS "被リンク数"
FROM "concepts"
SORT length(file.inlinks) DESC
LIMIT 20
```

## 👤 著者ノート

```dataview
TABLE WITHOUT ID
  file.link AS "著者",
  affiliation AS "所属",
  research_field AS "分野"
FROM "authors"
SORT file.name ASC
```

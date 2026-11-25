from django.urls import reverse

# (section title, [(label, url name, bootstrap icon)])
NAVIGATION = [
    ("Principal", [("Início", "core:home", "house")]),
    (
        "Financeiro",
        [
            ("Dashboard", "finance:dashboard", "graph-up"),
            ("Auditoria", "finance:audit", "table"),
            ("Categorias", "finance:categories", "tags"),
        ],
    ),
    ("Recibos", [("Recibos", "receipts:list", "receipt")]),
    (
        "Contratos",
        [
            ("Criador (IA)", "contracts:creator", "magic"),
            ("Contratos gerados", "contracts:generated_list", "file-earmark-text"),
            ("Modelos", "contracts:templates", "collection"),
            ("Arquivo de contratos", "contracts:archive", "archive"),
            ("Assinaturas", "contracts:signatures", "pen"),
        ],
    ),
    ("Mercado", [("Análise de ativos", "market:analyzer", "bar-chart-line")]),
]


def navigation(request):
    current = request.path
    sections = []
    for title, items in NAVIGATION:
        entries = [
            {"label": label, "url": reverse(url_name), "icon": icon, "active": False}
            for label, url_name, icon in items
        ]
        sections.append({"title": title, "items": entries})
    # Highlight only the most specific match (/financeiro/ vs /financeiro/auditoria/).
    matches = [
        e for s in sections for e in s["items"]
        if (current == e["url"] if e["url"] == "/" else current.startswith(e["url"]))
    ]
    if matches:
        max(matches, key=lambda e: len(e["url"]))["active"] = True
    return {"nav_sections": sections}

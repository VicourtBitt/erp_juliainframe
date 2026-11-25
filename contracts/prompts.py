"""Prompt used to ask the AI for a contract (ported from const/templates.py)."""

CONTRACT_CSS = """<style>:root{--accent:#0056b3;--text:#333;--bg:#fff;--muted:#6b6b6b;--divider:#dcdfe3;--font-sans:"Inter",Arial,sans-serif;--font-serif:"Merriweather",Georgia,serif}body{font-family:var(--font-sans);line-height:1.6;margin:40px auto;max-width:800px;padding:0 20px;background:var(--bg);color:var(--text)}h1{font-size:1.4rem;font-weight:700;color:var(--text);margin-bottom:1.5rem;padding-bottom:0;border-bottom:none;text-align:center;text-transform:uppercase}h2{font-size:1.2rem;font-weight:700;color:var(--text);margin-top:2rem;margin-bottom:1rem;text-align:left}p{margin-bottom:1rem;text-align:justify}.party-block,.clause-block{margin-bottom:1.5rem;padding:0;border:none;background:none}.party-block p,.clause-block p{margin-bottom:.5rem}ul{margin:.5rem 0 .5rem 1.5rem;padding-left:1.5rem}ul ul,ul ol{margin-top:.5rem;margin-bottom:.5rem}ol{margin:.5rem 0 .5rem 2.5rem;padding-left:0;list-style-type:none;counter-reset:item}ol ol{margin-top:.5rem;margin-bottom:.5rem}ol>li{counter-increment:item;position:relative;padding-left:.5rem;margin-bottom:.5rem}ol>li::before{content:counters(item,".") ". ";position:absolute;left:-2.5rem;width:2.2rem;text-align:right;font-weight:600;color:var(--text)}strong{font-weight:600;color:var(--text)}.signatures{display:flex;justify-content:space-around;gap:2rem;margin-top:3rem;padding-top:2rem;border-top:1px solid var(--divider);flex-wrap:wrap}.signature-block{text-align:center;width:45%;min-width:260px}.signature-line{border-bottom:1px solid var(--text);margin-bottom:6px;height:1px}.field-block{margin-bottom:12px}.field-block label{display:inline-block;width:140px;font-weight:600;margin-right:8px;color:var(--text)}.field-block span{color:var(--text)}.note{font-size:.9rem;color:var(--muted);font-style:italic;background:none;border:none;padding:.5rem 0;margin:.75rem 0}@media print{body{margin:0;padding:1rem;max-width:100%}}</style>"""

SYSTEM_INSTRUCTIONS = f"""
### SYSTEM ROLE & OBJECTIVE
You are a meticulous Legal Contract Drafting Engine. Your ONLY purpose is to structure a valid legal contract based on user input and output it in a strict format.
You must adopt the persona of a Senior Legal Counsel: formal, precise, objective, and authoritative.
Write the contract in the same language as the user's request (default: Brazilian Portuguese).

### JURISDICTION & COMPLIANCE
1. **Unspecified Jurisdiction:** If no specific law is cited, draft based on Brazilian law (Código Civil / CDC).
2. **Specified Jurisdiction:** If a location (e.g., "Brazil", "California") is mentioned, you MUST strictly adhere to the local statutory requirements.

### DRAFTING RULES
1. **Use Legal Terms of Art** appropriately.
2. **Dynamic Fields (Jinja2):** You must not invent data. If a specific name, date, amount, or value is not provided by the user, create a Jinja2 placeholder variable (e.g., `{{{{ client_name }}}}`). Variable names must be lowercase snake_case ASCII identifiers.
3. **Simple variables only:** Use only `{{{{ variable }}}}` substitutions — no filters, loops, conditionals or other Jinja statements.
4. **Variable Consistency:** Ensure the Jinja variables in the HTML match the list in the JSON output exactly.

### CRITICAL FORMATTING RULES
1. **NO CONVERSATION:** Do not output greetings, explanations, or "Here is your contract".
2. **RAW TEXT ONLY:** Output raw Unicode characters (e.g., 'ã', 'ç'). **NEVER** output Unicode escape sequences (like '\\u00e3').
3. **NO SCRIPTS:** Never include <script> tags, event handlers or external resources.
4. **THREE BLOCKS:** Provide exactly three Markdown code blocks in this order:
   - Block 1: `html` (the full contract document).
   - Block 2: `plaintext` (the contract title).
   - Block 3: `json` (the list of Jinja variables used, as {{"context_fields": [...]}}).

### CSS INJECTION
Insert the following CSS exactly as written into the `<style>` tag of the HTML head:
{CONTRACT_CSS}
"""

EXAMPLE = """
### EXAMPLE OUTPUT
User Input: "Create a simple NDA for a freelancer named John Doe."

Response:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Non-Disclosure Agreement</title>
    <style>... (The CSS provided in instructions) ...</style>
</head>
<body>
    <h1>NON-DISCLOSURE AGREEMENT</h1>
    <div class="section">
        <h2>PARTIES</h2>
        <div class="party-block">
            <p><strong>DISCLOSING PARTY:</strong> {{ disclosing_party_name }}, located at {{ disclosing_party_address }}.</p>
            <p><strong>RECEIVING PARTY:</strong> <strong>John Doe</strong>, located at {{ receiving_party_address }}.</p>
        </div>
    </div>
    <div class="section">
        <h2>1. CONFIDENTIALITY</h2>
        <div class="clause-block">
            <p><strong>1.1.</strong> The Receiving Party agrees to not disclose confidential information for a period of {{ confidentiality_term }} years.</p>
        </div>
    </div>
    <div class="signatures">
        <div class="signature-block"><div class="signature-line"></div><p>{{ disclosing_party_name }}</p></div>
        <div class="signature-block"><div class="signature-line"></div><p>John Doe</p></div>
    </div>
</body>
</html>
```

```plaintext
Non-Disclosure Agreement
```

```json
{
    "context_fields": [ "disclosing_party_name", "disclosing_party_address", "receiving_party_address", "confidentiality_term" ]
}
```
"""

CREATOR_PLACEHOLDER = """Descreva o contrato que você deseja e clique em "Gerar contrato com IA". Por exemplo:

Gere um contrato de prestação de serviços para um desenvolvedor web freelancer que irá criar um site para uma pequena empresa.
O contrato deve possuir:
  - Descrição detalhada dos serviços a serem prestados
  - Prazos para entrega
  - Valor total e condições de pagamento
  - Cláusulas de confidencialidade
  - Direitos autorais sobre o trabalho produzido
  - Condições para rescisão do contrato

Nota: sempre consulte um advogado para revisar contratos legais."""


def build_contract_prompt(context: str) -> str:
    return f"{SYSTEM_INSTRUCTIONS}\n{EXAMPLE}\n### USER REQUEST\n{context}\n\nGenerate the contract as per the above request."

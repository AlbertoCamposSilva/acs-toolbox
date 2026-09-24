from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_referencia_da_skill_igual_a_documentacao():
    # A skill leva uma cópia de docs/acs_toolbox.md; atualize com:
    #   cp docs/acs_toolbox.md skills/acs-toolbox/references/api.md
    docs = (RAIZ / "docs" / "acs_toolbox.md").read_text(encoding="utf-8")
    copia = (RAIZ / "skills" / "acs-toolbox" / "references" / "api.md").read_text(encoding="utf-8")
    assert copia == docs


def test_skill_tem_frontmatter():
    texto = (RAIZ / "skills" / "acs-toolbox" / "SKILL.md").read_text(encoding="utf-8")
    assert texto.startswith("---\nname: acs-toolbox\ndescription: ")

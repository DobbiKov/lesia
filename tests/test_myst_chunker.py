from lesia.doc_translator_mod.myst_chunker import split_myst_document_into_chunks


def test_target_label_travels_with_the_heading_it_labels() -> None:
    source = (
        "### Demander un environnement\n"
        "\n"
        "Pour demander un environnement, l'utilisateur peut au choix :\n"
        "\n"
        "- le selectionner depuis son tableau de bord s'il l'a deja utilise;\n"
        "- ouvrir une [**activite myDocker**](#activite_lti) depuis un ENT.\n"
        "\n"
        "(dossiers_personnels)=\n"
        "\n"
        "### Dossiers personnels\n"
        "\n"
        "Chaque utilisateur dispose d'un dossier personnel.\n"
    )

    chunks = split_myst_document_into_chunks(source)

    assert len(chunks) == 2
    assert "(dossiers_personnels)=" not in chunks[0]["content"]
    assert chunks[1]["content"].startswith("(dossiers_personnels)=")
    assert "### Dossiers personnels" in chunks[1]["content"]


def test_multiple_consecutive_target_labels_travel_with_the_heading() -> None:
    source = (
        "### First heading\n"
        "\n"
        "Some text.\n"
        "\n"
        "(label-one)=\n"
        "(label-two)=\n"
        "\n"
        "### Second heading\n"
        "\n"
        "More text.\n"
    )

    chunks = split_myst_document_into_chunks(source)

    assert len(chunks) == 2
    assert "(label-one)=" not in chunks[0]["content"]
    assert "(label-two)=" not in chunks[0]["content"]
    assert chunks[1]["content"].startswith("(label-one)=\n(label-two)=\n")


def test_trailing_target_label_with_no_following_heading_is_kept() -> None:
    source = (
        "### Only heading\n"
        "\n"
        "Some text.\n"
        "\n"
        "(dangling-label)=\n"
    )

    chunks = split_myst_document_into_chunks(source)

    assert len(chunks) == 1
    assert "(dangling-label)=" in chunks[0]["content"]

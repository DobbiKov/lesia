import logging
import xml.etree.ElementTree as ET


def verify_placeholders(translated_xml: str, expected_phs: dict[str, str]) -> tuple[list[str], list[str]]:
    """Check that the translated XML contains exactly the expected <PH> IDs.

    Args:
        translated_xml: The XML string returned by the LLM.
        expected_phs: Placeholder map produced before translation (id -> original content).

    Returns:
        tuple[list[str], list[str]]: (missing_ids, extra_ids) — both empty means OK.
    """
    try:
        root = ET.fromstring(translated_xml)
    except ET.ParseError:
        return [], []  # ParseError is handled separately; don't double-report here.

    found_ids = {elem.get("id") for elem in root.iter("PH") if elem.get("id")}
    expected_ids = set(expected_phs.keys())

    missing = sorted(expected_ids - found_ids, key=lambda x: int(x) if x.isdigit() else x)
    extra = sorted(found_ids - expected_ids, key=lambda x: int(x) if x.isdigit() else x)

    return missing, extra


def reconstruct_from_xml(translated_xml: str, phs: dict[str, str] | None = None) -> str:
    """
    Rebuilds the source document from a translated XML file that uses a
    single <TEXT> tag with mixed content (text nodes and <PH> elements).

    This function correctly interprets the .text and .tail attributes of
    child elements within the <TEXT> tag to reconstruct the document in the
    correct order.

    Args:
        translated_xml (str): The XML string from the translation process.
                              It is expected to contain a <document><TEXT>...</TEXT></document> structure.
        phs (dict[str, str] | None): Placeholder map (id -> original content).
    Returns:
        str: The fully reconstructed document with translated text and original placeholders.
    """
    if phs is None:
        phs = {}
    try:
        root = ET.fromstring(translated_xml)
    except ET.ParseError as e:
        logging.error(f"Failed to parse translated XML: {e}")
        logging.error(f"XML Content that failed:\n{translated_xml}")
        raise

    # Find the main <TEXT> container tag.
    text_container = root.find('TEXT')
    if text_container is None:
        logging.warning("Could not find a <TEXT> tag in the provided XML. Returning an empty string.")
        return ""

    reconstructed_parts = []

    # 1. Start with the initial text of the <TEXT> tag itself.
    # This is the text before the very first <PH> child element.
    if text_container.text:
        reconstructed_parts.append(text_container.text)

    # 2. Iterate through all child elements (<PH> tags) within <TEXT>.
    for element in text_container:
        # A. Append the content of the placeholder itself.
        if element.tag == 'PH':
            try:
                ph_id = element.get("id")
                if ph_id and ph_id in phs:
                    reconstructed_parts.append(phs[ph_id])
                else:
                    orig = element.text or ""
                    if orig is None:
                        logging.warning("Original contents of the <PH> tag is not found!")
                    else:
                        if ph_id:
                            logging.warning("Original contents of the <PH> tag is not found in placeholder map!")
                        reconstructed_parts.append(orig)
            except Exception:
                logging.warning("Original contents of the <PH> tag is not found!")
        else:
            logging.warning(f"Unexpected tag <{element.tag}> found inside <TEXT>. It will be ignored.")

        # B. Append the text that immediately follows the placeholder.
        # This is the "tail" text of the element.
        if element.tail:
            reconstructed_parts.append(element.tail)

    return "".join(reconstructed_parts)


def create_translation_xml(segments: list[tuple[str, str]]) -> tuple[str, dict, bool]:
    """
    Converts parsed segments into a single <TEXT> tag containing mixed content
    (text and <PH> tags), which is ideal for translation.

    - Merges consecutive non-text segments into single <PH> tags.
    - Creates one top-level <TEXT> tag.
    - Places text nodes and <PH> elements inside the <TEXT> tag.
    - Assigns sequential "id" attributes to each <PH> tag.
    - Stores the placeholder content in the returned map for reconstruction.
      (The <PH> tags also keep their original text content.)

    Returns:
        tuple[str, dict, bool]:
            - XML string for translation (<document><TEXT>...</TEXT></document>).
            - Placeholder map: id -> original placeholder content.
            - ph_only: True if there is no translatable text, only placeholders.
    """
    ph_only = len([1 for el in segments if el[0] == 'text']) == 0
    # -- Step 1: Coalesce consecutive placeholders --
    # Consecutive placeholder segments are merged into one <PH> tag, EXCEPT for
    # bare '\n' placeholders which are kept as individual tags so that structural
    # line breaks are never silently absorbed into surrounding syntax.
    merged_segments = []
    pending: list[str] = []   # accumulates non-'\n' placeholder content

    def _flush_pending() -> None:
        if pending:
            merged = "".join(pending)
            if merged:
                merged_segments.append(('placeholder', merged))
            pending.clear()

    for seg_type, content in segments:
        if seg_type == 'text':
            _flush_pending()
            merged_segments.append(('text', content))
        elif content == '\n':
            # Bare newline placeholder: flush any accumulated content first,
            # then emit this newline as its own placeholder.
            _flush_pending()
            merged_segments.append(('placeholder', '\n'))
        else:
            # Regular placeholder: accumulate for merging with neighbours.
            pending.append(content)

    _flush_pending()


    # -- Step 2: Build the Mixed-Content XML --
    root = ET.Element('document')
    # All content will go inside a single <TEXT> tag
    text_container = ET.SubElement(root, 'TEXT')

    placeholders = {}
    ph_id = 1
    last_element = None # Keep track of the last <PH> element added

    for seg_type, content in merged_segments:
        if seg_type == 'text':
            if last_element is not None:
                # If text follows a <PH> tag, it becomes the .tail of that tag.
                last_element.tail = (last_element.tail or '') + content
            else:
                # If it's the first piece of text, it becomes the .text of the container.
                text_container.text = (text_container.text or '') + content

        elif seg_type == 'placeholder':
            # Create the placeholder element
            current_ph_id = str(ph_id)
            ph_elem = ET.SubElement(text_container, 'PH', id=current_ph_id)
            ph_elem.text = content

            placeholders[current_ph_id] = content
            ph_id += 1
            last_element = ph_elem # This is now the most recent element

    # -- Step 3: Finalize and Save --
    # Use method='xml' and short_empty_elements=True for self-closing tags like <PH ... />
    xml_string = ET.tostring(root, encoding='unicode', method='xml', short_empty_elements=True)

    # Ensure the output directory exists
    # output_dir.mkdir(parents=True, exist_ok=True)

    return xml_string, placeholders, ph_only

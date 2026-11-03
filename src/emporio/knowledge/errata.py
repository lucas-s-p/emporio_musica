"""Known conflicts inside the manual, attached to the section where the conflict appears.

The notes tell the model which source wins, so it never has to resolve a contradiction itself.
Each one is also listed in the README as an assumption.
"""

ERRATA: dict[str, str] = {
    "1.2": (
        "The email is printed with an accent (contato@empóriodamusica.com.br), which is not a "
        "valid address. Use the email from get_store_info."
    ),
    "3": (
        "The table says a minimum installment of R$ 100 for any count. Section 3.1 is more "
        "specific and wins. Use get_payment_options for the real installment options."
    ),
    "4.2": (
        "Defect exchange is 30 days from purchase. The legal warranty (section 8.1) is 90 days "
        "from receipt. check_return_eligibility returns both routes for an order."
    ),
    "5.1": (
        "'Above R$ 500' leaves exactly R$ 500 undefined. The store treats R$ 500 as free "
        "shipping. Use estimate_shipping for the exact fee."
    ),
    "6.1": (
        "These are general campaign descriptions. A discount exists only if the product price "
        "from the data tools shows a promotion. Never promise a campaign discount."
    ),
    "7": (
        "The WhatsApp number printed here differs from the official company phone in section "
        "1.2. Use the phone from get_store_info."
    ),
}

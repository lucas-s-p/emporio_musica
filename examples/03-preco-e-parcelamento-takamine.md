# Preço e parcelamento: Takamine GD20

_Data de hoje fixada em 02/11/2026. Modelo: nvidia/nemotron-3.5-super-vl:free. Gerado por scripts/generate_examples.py._

**Cliente:** Quanto custa o Takamine GD20?

Ferramentas usadas:
- `search_products(query="Takamine GD20")` devolveu `{"total_matches": 1, "returned": 1, "products": [{"product_id": 95, "name": "Takamine GD20 Dreadnought Natural", "brand": "Takamine", "category": "Violões", "availability": "in_stock", "stock_quantity": 5, "list_price": "2199.00", "price": "2199.00", "pix_price": "2089.05", "pix_discount_applies": t...`

**Agente:** O Takamine GD20 Dreadnought Natural custa R$ 2.199,00. No pagamento à vista pelo PIX, sai por R$ 2.089,05. Tem 5 unidades em estoque.

**Cliente:** E no cartão, em 10x, quanto fica cada parcela?

Ferramentas usadas:
- `get_payment_options(items=[{"product_id": 95, "quantity": 1}])` devolveu `{"card_total": "2199.00", "pix_total": "2089.05", "installments_interest_free": [{"count": 1, "value": "2199.00"}, {"count": 2, "value": "1099.50"}, {"count": 3, "value": "733.00"}, {"count": 4, "value": "549.75"}, {"count": 5, "value": "439.80"}, {"count": 6, "value": "366.50"}, {"count": 7, "value...`

**Agente:** No cartão, em 10x sem juros, cada parcela fica R$ 219,90.

<!-- собирает qa-scan (route.py index) — руками не правь -->
# Кейсы по требованиям

Ключ требования или задачи (Jira и т.п.) → кейсы. Ищи: `grep -n "SHOP-12" by-requirement.md`.

## SHOP-12 (2)

- [TC-0001](../oformlenie-zakaza/TC-0001-oformlenie-zakaza-iz-korziny.md) Оформление заказа из корзины · highest · ready · automated · cap: order-checkout · req: SHOP-12, SHOP-15
- [TC-0002](../oformlenie-zakaza/TC-0002-pustoy-zakaz-ne-oformlyaetsya.md) Пустой заказ не оформляется · medium · ready · automated · cap: order-checkout · req: SHOP-12

## SHOP-15 (1)

- [TC-0001](../oformlenie-zakaza/TC-0001-oformlenie-zakaza-iz-korziny.md) Оформление заказа из корзины · highest · ready · automated · cap: order-checkout · req: SHOP-12, SHOP-15

## SHOP-31 (1)

- [TC-0004](../otmena-zakaza/pokupatel/TC-0004-pokupatel-ne-mozhet-otmenit-oplachennyy.md) Покупатель не может отменить оплаченный заказ · high · ready · automated · cap: order-cancellation · req: SHOP-31

## без требований (5)

- [TC-0003](../oformlenie-zakaza/TC-0003-zakaz-bolshe-50-pozitsiy.md) Заказ больше 50 позиций · high · ready · cap: order-checkout
- [TC-0005](../otmena-zakaza/pokupatel/TC-0005-otmena-neoplachennogo-zakaza.md) Отмена неоплаченного заказа · medium · ready · cap: order-cancellation
- [TC-0006](../otmena-zakaza/menedzher/TC-0006-menedzher-otmenyaet-oplachennyy-zakaz-s.md) Менеджер отменяет оплаченный заказ с возвратом · highest · ready · cap: order-cancellation
- [TC-0007](../dostavka/TC-0007-peredacha-zakaza-na-sklad.md) Передача заказа на склад · low · ready · cap: order-shipping
- [TC-0008](../dostavka/TC-0008-peredacha-zakaza-na-sklad.md) Передача заказа на склад · low · ready · cap: order-shipping

from app import create_app, db
from app.models import Banco


def seed_bancos():
    bancos = [
        (1, "Banco de Chile"),
        (9, "Banco Internacional"),
        (12, "BancoEstado"),
        (14, "Scotiabank"),
        (16, "Banco de Crédito e Inversiones"),
        (27, "Corpbanca"),
        (28, "Banco Bice"),
        (31, "HSBC Bank"),
        (37, "Banco Santander-Chile"),
        (39, "Banco Itaú"),
        (49, "Banco Security"),
        (51, "Banco Falabella"),
        (52, "Deutsche Bank"),
        (53, "Banco Ripley"),
        (54, "Rabobank Chile"),
        (55, "Banco Consorcio"),
        (56, "Banco Penta"),
        (57, "Banco París"),
        (504, "Banco BBVA"),
        (672, "Coopeuch"),
        (729, "Los Héroes"),
        (732, "Tapp Caja Los Andes"),
        (730, "Tenpo Prepago"),
        (875, "Mercado Pago"),
        (741, "Copec Pay"),
    ]

    # 👇 IMPORTANTE: aquí asumimos que el modelo Banco tiene campos:
    # id (PK autoincremental) y opcionalmente 'codigo' y 'nombre'.
    # Si tienes un campo 'codigo', usamos ese; si no, solo se guarda el nombre.

    for codigo, nombre in bancos:
        # Si el modelo tiene columna 'codigo', buscamos por código.
        if hasattr(Banco, "codigo"):
            existente = Banco.query.filter_by(codigo=codigo).first()
        else:
            existente = Banco.query.filter_by(nombre=nombre).first()

        if not existente:
            data = {"nombre": nombre}
            if hasattr(Banco, "codigo"):
                data["codigo"] = codigo
            banco = Banco(**data)
            db.session.add(banco)

    db.session.commit()
    print("✔ Bancos cargados correctamente.")


def main():
    app = create_app()
    with app.app_context():
        seed_bancos()


if __name__ == "__main__":
    main()

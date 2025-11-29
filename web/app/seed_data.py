from app import create_app, db
from app.models import AFP, Salud, Banco, CajaCompensacion


def get_or_create(model, **kwargs):
    instance = model.query.filter_by(**kwargs).first()
    if instance:
        return instance, False
    instance = model(**kwargs)
    db.session.add(instance)
    return instance, True


def seed_afp():
    afps = [
        "AFP Habitat",
        "AFP Provida",
        "AFP Capital",
        "AFP Cuprum",
        "AFP Modelo",
        "AFP PlanVital",
        "AFP UNO",
    ]
    for nombre in afps:
        get_or_create(AFP, nombre=nombre)


def seed_salud():
    # tipo: FONASA / ISAPRE
    fonasa, _ = get_or_create(Salud, nombre="FONASA", tipo="FONASA")

    isapres = [
        "Colmena",
        "Consalud",
        "Cruz Blanca",
        "Nueva Masvida",
        "Banmédica",
        "Vida Tres",
    ]
    for nombre in isapres:
        get_or_create(Salud, nombre=nombre, tipo="ISAPRE")


def seed_bancos():
    bancos = [
        "Banco de Chile",
        "Banco Santander",
        "Banco BCI",
        "Scotiabank",
        "Banco Estado",
        "Banco Itaú",
        "Banco Security",
        "Banco BICE",
        "Banco Falabella",
        "Banco Ripley",
        "Banco Consorcio",
    ]
    for nombre in bancos:
        get_or_create(Banco, nombre=nombre)


def seed_cajas_compensacion():
    cajas = [
        "Caja Los Andes",
        "Caja La Araucana",
        "Caja Gabriela Mistral",
        "Caja 18 de Septiembre",
        "Caja Los Héroes",
    ]
    for nombre in cajas:
        get_or_create(CajaCompensacion, nombre=nombre)


def main():
    app = create_app()
    with app.app_context():
        seed_afp()
        seed_salud()
        seed_bancos()
        seed_cajas_compensacion()
        db.session.commit()
        print("Tablas maestras pobladas correctamente.")


if __name__ == "__main__":
    main()

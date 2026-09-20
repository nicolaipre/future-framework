# Seeders — base class, discovery, and generation.


import importlib.util

from pathlib import Path
from types import UnionType
from typing import get_args, get_origin, Union

from future.interfaces.IModel import IModel
from future.migrations import MigrationGenerator


class Seeder:
    async def run(self):
        raise NotImplementedError

    async def call(self, seeder_class):
        await seeder_class().run()


class SeedRunner:
    def __init__(self, path):
        self.path = path

    def discover(self):
        seeders = {}
        directory = Path(self.path)
        if not directory.exists():
            return seeders
        for file_path in sorted(directory.glob("*.py")):
            if file_path.name.startswith("_"):
                continue
            module_name = f"seeder_{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for value in module.__dict__.values():
                if isinstance(value, type) and issubclass(value, Seeder) and value is not Seeder:
                    seeders[value.__name__] = value
        return seeders

    async def run(self, name=None):
        seeders = self.discover()
        if name is not None:
            if name not in seeders:
                raise ValueError(f"Seeder not found: {name}")
            await seeders[name]().run()
            return [name]
        ran = []
        for seeder_name in sorted(seeders.keys()):
            await seeders[seeder_name]().run()
            ran.append(seeder_name)
        return ran


class SeedGenerator:
    def __init__(self, models_path="app/models", seeds_path="database/seeds"):
        self.models_path = models_path
        self.seeds_path = seeds_path

    def find_model(self, name):
        for model in MigrationGenerator(models_path=self.models_path).discover_models():
            if model.__name__ == name:
                return model
        raise ValueError(f"Model not found: {name}")

    def value_expr(self, field, annotation):
        origin = get_origin(annotation)
        if origin is Union or origin is UnionType:
            args = [arg for arg in get_args(annotation) if arg is not type(None)]
            annotation = args[0] if args else str
        type_name = getattr(annotation, "__name__", str(annotation))
        if field == "id":
            return "fake.uuid4()"
        if field in ("timestamp", "published_at", "generated_at", "joined_at", "trades_synced_at", "last_login_at"):
            return 'fake.date_time_between(start_date="-1y", end_date="now")'
        if type_name == "datetime":
            return "fake.date_time_this_year()"
        if field == "historical_trades_offset":
            return "0"
        if field in ("follower_count", "following_count"):
            return "fake.random_int(0, 5000)"
        if field == "average_hold_time":
            return "fake.random_int(1, 365)"
        if field == "rating":
            return "fake.random_int(0, 5)"
        if field == "window_hours":
            return "fake.random_int(1, 168)"
        if field == "unique_traders":
            return "fake.random_int(2, 20)"
        if type_name == "int":
            return "fake.random_int(1, 9999)"
        if field == "price":
            return "float(fake.pyfloat(min_value=5, max_value=1500, right_digits=2))"
        if field == "percentage_change":
            return "float(fake.pyfloat(min_value=-25, max_value=25, right_digits=2))"
        if field == "strength":
            return "float(fake.pyfloat(min_value=0, max_value=100, right_digits=2))"
        if type_name == "float":
            return "float(fake.pyfloat(min_value=1, max_value=100))"
        if type_name == "bool":
            return "fake.boolean()"
        if field.endswith("_id"):
            return "str(fake.random_int(1000, 9999))"
        if "email" in field:
            return "fake.email()"
        if field == "firstname":
            return "fake.first_name()"
        if field == "lastname":
            return "fake.last_name()"
        if field == "instrument_name":
            return "fake.company()"
        if field == "symbol":
            return 'fake.lexify(text="????").upper()'
        if field in ("logo_url", "image_url", "avatar_uri"):
            return "fake.image_url()"
        if field == "url":
            return "fake.url()"
        if field == "currency":
            return 'fake.random_element(elements=("NOK", "SEK", "DKK", "EUR", "USD"))'
        if field == "language":
            return 'fake.random_element(elements=("nb", "sv", "da", "en"))'
        if field == "trade_type" or field == "side":
            return 'fake.random_element(elements=("BUY", "SELL"))'
        if field == "percentage_change_interval":
            return 'fake.random_element(elements=("TODAY", "ONE_WEEK", "ONE_MONTH", "THREE_MONTHS", "ONE_YEAR"))'
        if field == "group_type":
            return 'fake.random_element(elements=("COMMON_SHARE", "FUND", "ETF", "WARRANT"))'
        if field == "kind":
            return 'fake.random_element(elements=("instruments", "users"))'
        if field == "members":
            return "fake.json()"
        if field == "title":
            return "fake.sentence(nb_words=8)"
        if field in ("summary", "reason"):
            return "fake.sentence()"
        if field == "password_hash":
            return "fake.sha256()"
        if "name" in field or "username" in field:
            return "fake.user_name()"
        if field in ("description", "text", "body", "content") or field.endswith("_original") or field.endswith("_translated"):
            return "fake.paragraph()"
        return "fake.word()"

    def render(self, model):
        name = model.__name__
        annotations = dict(getattr(model, "__annotations__", {}))
        args = []
        for field, annotation in annotations.items():
            current = annotation
            origin = get_origin(annotation)
            if origin is Union or origin is UnionType:
                non_null = [arg for arg in get_args(annotation) if arg is not type(None)]
                current = non_null[0] if non_null else str
            if isinstance(current, type) and issubclass(current, IModel):
                continue
            args.append(f"                {field}={self.value_expr(field, annotation)},")
        if args:
            construct = f"            await {name}(\n" + "\n".join(args) + f"\n            ).save()"
        else:
            construct = f"            await {name}().save()"
        return (
            "from faker import Faker\n"
            "from future.seeder import Seeder\n"
            f"from app.models.{name} import {name}\n"
            "\n"
            "\n"
            f"class {name}Seeder(Seeder):\n"
            "    async def run(self):\n"
            "        fake = Faker()\n"
            "        for _ in range(10):\n"
            f"{construct}\n"
        )

    def make(self, model_name=None):
        if model_name is None:
            return self.make_all()
        model = self.find_model(model_name)
        return [self.write(model)]

    def make_all(self):
        paths = []
        for model in MigrationGenerator(models_path=self.models_path).discover_models():
            path = self.write(model, skip_existing=True)
            if path is not None:
                paths.append(path)
        return paths

    def write(self, model, skip_existing=False):
        class_name = f"{model.__name__}Seeder"
        directory = Path(self.seeds_path)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{class_name}.py"
        if path.exists():
            if skip_existing:
                return None
            raise FileExistsError(f"File already exists: {path}")
        path.write_text(self.render(model))
        return str(path)

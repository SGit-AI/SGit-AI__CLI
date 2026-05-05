from osbot_utils.type_safe.Type_Safe import Type_Safe

class Migration__Registry(Type_Safe):
    def all_migrations(self) -> list:
        from sgit_ai.migrations.tree_iv.Migration__Tree_IV_Determinism import Migration__Tree_IV_Determinism
        return [Migration__Tree_IV_Determinism()]

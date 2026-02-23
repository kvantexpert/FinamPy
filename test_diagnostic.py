try:
    from FinamPy import FinamPy
    print("✓ FinamPy импортирован")
    
    from core.diagnostic import Diagnostic
    print("✓ Diagnostic импортирован")
    
    # Попробуем создать экземпляр
    fp_provider = FinamPy()
    diag = Diagnostic(fp_provider)
    print("✓ Diagnostic создан")
    
    # Проверим метод
    if hasattr(diag, 'run_all'):
        print("✓ Метод run_all существует")
    else:
        print("✗ Метод run_all отсутствует")
        print(f"Доступные методы: {[m for m in dir(diag) if not m.startswith('_')]}")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
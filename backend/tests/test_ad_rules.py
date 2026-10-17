from app.ad_rules import AD_SECONDS, calculate_ad_plan


def test_video_corto_pide_un_anuncio():
    plan = calculate_ad_plan(90)  # 1.5 min
    assert plan.allowed and plan.ads_required == 1


def test_justo_5_minutos_sigue_siendo_un_anuncio():
    assert calculate_ad_plan(300).ads_required == 1


def test_5_minutos_y_un_segundo_pide_dos():
    assert calculate_ad_plan(301).ads_required == 2


def test_15_minutos_pide_tres_anuncios():
    plan = calculate_ad_plan(15 * 60)
    assert plan.allowed and plan.ads_required == 3
    assert plan.total_ad_seconds == 3 * AD_SECONDS


def test_video_de_30_minutos_no_entra_al_plan_gratis():
    plan = calculate_ad_plan(30 * 60)
    assert not plan.allowed and plan.ads_required == 0


def test_duracion_invalida():
    assert not calculate_ad_plan(0).allowed

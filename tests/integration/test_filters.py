"""Integration tests for listing, filtering, facets, search, and annotations.

Location and time filtering are exercised explicitly and in combination, since
those are the contextual filters the spec calls out by name.
"""

from app.backend.schemas import GarmentType, LocationContext, Occasion, Season


def ids(response):
    return {img["id"] for img in response.json()}


class TestAttributeFilters:
    def test_no_filters_returns_all(self, client, seed):
        a, b = seed(), seed()
        assert ids(client.get("/api/images")) == {a, b}

    def test_filter_by_garment_type(self, client, seed):
        jacket = seed(garment_type=GarmentType.JACKET)
        seed(garment_type=GarmentType.DRESS)
        assert ids(client.get("/api/images?garment_type=jacket")) == {jacket}

    def test_filter_by_season(self, client, seed):
        summer = seed(season=Season.SUMMER)
        seed(season=Season.WINTER)
        assert ids(client.get("/api/images?season=summer")) == {summer}

    def test_filter_by_designer(self, client, seed):
        lia = seed(designer="lia")
        seed(designer="sam")
        assert ids(client.get("/api/images?designer=lia")) == {lia}


class TestColorFilter:
    def test_filter_by_color(self, client, seed):
        red = seed(color_palette=["red", "black"])
        seed(color_palette=["indigo", "white"])
        assert ids(client.get("/api/images?color=red")) == {red}

    def test_color_match_is_whole_token_not_substring(self, client, seed):
        # "redwood" must not be returned for a "red" query
        seed(color_palette=["redwood"])
        assert ids(client.get("/api/images?color=red")) == set()


class TestLocationFilters:
    def test_filter_by_country(self, client, seed):
        fr = seed(location_context=LocationContext(country="France"))
        seed(location_context=LocationContext(country="Japan"))
        assert ids(client.get("/api/images?country=France")) == {fr}

    def test_filter_by_continent(self, client, seed):
        eu = seed(location_context=LocationContext(continent="Europe"))
        seed(location_context=LocationContext(continent="Asia"))
        assert ids(client.get("/api/images?continent=Europe")) == {eu}

    def test_studio_shot_with_null_location_excluded(self, client, seed):
        seed(location_context=LocationContext(country="France"))
        seed(location_context=LocationContext())  # studio, no location
        assert len(client.get("/api/images?country=France").json()) == 1


class TestTimeFilters:
    def test_filter_by_year(self, client, seed):
        old = seed(year=2024)
        seed(year=2026)
        assert ids(client.get("/api/images?year=2024")) == {old}

    def test_filter_by_month(self, client, seed):
        jan = seed(month=1)
        seed(month=6)
        assert ids(client.get("/api/images?month=1")) == {jan}


class TestCombinedFilters:
    def test_location_and_time_together(self, client, seed):
        target = seed(location_context=LocationContext(country="France"), year=2025)
        seed(location_context=LocationContext(country="France"), year=2026)
        seed(location_context=LocationContext(country="Japan"), year=2025)
        assert ids(client.get("/api/images?country=France&year=2025")) == {target}

    def test_attribute_and_designer_together(self, client, seed):
        target = seed(garment_type=GarmentType.DRESS, designer="lia")
        seed(garment_type=GarmentType.DRESS, designer="sam")
        seed(garment_type=GarmentType.JACKET, designer="lia")
        got = client.get("/api/images?garment_type=dress&designer=lia")
        assert ids(got) == {target}


class TestFullTextSearch:
    def test_search_matches_description(self, client, seed):
        match = seed(description="cropped denim jacket with raw hem")
        seed(description="flowing silk evening gown")
        assert ids(client.get("/api/images?q=denim")) == {match}

    def test_search_is_prefix_matched(self, client, seed):
        match = seed(description="heavily embroidered neckline")
        assert ids(client.get("/api/images?q=embroider")) == {match}

    def test_search_matches_annotation_content(self, client, seed):
        img = seed(description="plain top")
        client.post(
            f"/api/images/{img}/annotations",
            json={"kind": "note", "content": "spotted at an artisan market"},
        )
        assert ids(client.get("/api/images?q=artisan")) == {img}

    def test_search_punctuation_does_not_error(self, client, seed):
        seed(description="plain top")
        # stray quotes/operators must not produce an FTS syntax error
        assert client.get('/api/images?q="art* OR').status_code == 200

    def test_search_combines_with_filter(self, client, seed):
        target = seed(description="denim jacket", garment_type=GarmentType.JACKET)
        seed(description="denim skirt", garment_type=GarmentType.SKIRT)
        got = client.get("/api/images?q=denim&garment_type=jacket")
        assert ids(got) == {target}


class TestFacets:
    def test_facets_reflect_seeded_data(self, client, seed):
        seed(garment_type=GarmentType.JACKET, occasion=Occasion.CASUAL)
        seed(garment_type=GarmentType.DRESS, occasion=Occasion.EVENING)
        facets = client.get("/api/filters").json()
        assert set(facets["garment_type"]) == {"dress", "jacket"}
        assert set(facets["occasion"]) == {"casual", "evening"}

    def test_facets_empty_when_no_data(self, client):
        facets = client.get("/api/filters").json()
        assert facets["garment_type"] == []

    def test_facets_split_colors_out_of_palette(self, client, seed):
        seed(color_palette=["indigo", "white"])
        seed(color_palette=["white", "black"])
        facets = client.get("/api/filters").json()
        assert set(facets["color"]) == {"black", "indigo", "white"}

    def test_facets_include_location_and_time(self, client, seed):
        seed(location_context=LocationContext(country="France"), year=2025)
        facets = client.get("/api/filters").json()
        assert facets["country"] == ["France"]
        assert facets["year"] == [2025]


class TestAnnotations:
    def test_create_and_list_annotation(self, client, seed):
        img = seed()
        created = client.post(
            f"/api/images/{img}/annotations",
            json={"kind": "tag", "content": "hero piece"},
        )
        assert created.status_code == 201
        listed = client.get(f"/api/images/{img}/annotations").json()
        assert [a["content"] for a in listed] == ["hero piece"]
        assert listed[0]["kind"] == "tag"

    def test_annotations_appear_in_image_detail(self, client, seed):
        img = seed()
        client.post(
            f"/api/images/{img}/annotations",
            json={"kind": "note", "content": "client favorite"},
        )
        detail = client.get(f"/api/images/{img}").json()
        assert len(detail["annotations"]) == 1

    def test_invalid_kind_rejected(self, client, seed):
        img = seed()
        resp = client.post(
            f"/api/images/{img}/annotations",
            json={"kind": "sketch", "content": "x"},
        )
        assert resp.status_code == 422

    def test_empty_content_rejected(self, client, seed):
        img = seed()
        resp = client.post(
            f"/api/images/{img}/annotations",
            json={"kind": "note", "content": ""},
        )
        assert resp.status_code == 422

    def test_annotation_on_missing_image_404(self, client):
        resp = client.post(
            "/api/images/999/annotations",
            json={"kind": "tag", "content": "x"},
        )
        assert resp.status_code == 404

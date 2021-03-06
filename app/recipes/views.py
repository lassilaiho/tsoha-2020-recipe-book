from flask import render_template, url_for, redirect, request, abort
from flask_login import current_user
from sqlalchemy.sql.expression import false

from app.main import app, db, login_required
from app.recipes.models import Recipe
from app.recipes.forms import EditRecipeForm, GetRecipesForm
from app.ingredients.models import Ingredient, RecipeIngredient
from app.ingredients.forms import RecipeIngredientForm


def render_edit_form(save_action: str, cancel_action: str, form: EditRecipeForm):
    initial_values = []
    groups = {}
    for recipe_ingredient in form.ingredient_amounts:
        group = groups.get(recipe_ingredient.form.group.data)
        if group is None:
            group = {
                "name": recipe_ingredient.form.group.data,
                "errors": set(),
                "ingredients": [],
            }
            groups[recipe_ingredient.form.group.data] = group
            initial_values.append(group)
        for error in recipe_ingredient.form.group.errors:
            group["errors"].add(error)
        group["ingredients"].append({
            "amount": recipe_ingredient.form.amount.data,
            "amountErrors": recipe_ingredient.form.amount.errors,
            "name": recipe_ingredient.form.name.data,
            "nameErrors": recipe_ingredient.form.name.errors,
        })
    for group in initial_values:
        group["errors"] = list(group["errors"])
    return render_template(
        "recipes/edit.html",
        save_action=save_action,
        cancel_action=cancel_action,
        form=form,
        ingredient_data=initial_values,
        is_str=lambda x: isinstance(x, str),
    )


@app.route("/recipes")
@login_required
def get_recipes():
    form = GetRecipesForm(request.args)
    if not form.validate():
        return render_template(
            "recipes/index.html",
            pagination=Recipe.query.filter_by(id=None).paginate(),
            form=form,
        )
    if form.query.data:
        filter = false()
        if not form.no_name.data:
            filter |= Recipe.name.contains(form.query.data, autoescape=True)
        if not form.no_description.data:
            filter |= Recipe.description.contains(
                form.query.data, autoescape=True)
        if not form.no_steps.data:
            filter |= Recipe.steps.contains(form.query.data, autoescape=True)
        filter &= Recipe.account_id == current_user.id
        recipes = Recipe.query.filter(filter).order_by(Recipe.name)
    else:
        recipes = Recipe.query.\
            filter_by(account_id=current_user.id).\
            order_by(Recipe.id.desc())
    form.toggle_filters()
    return render_template(
        "recipes/index.html",
        pagination=recipes.paginate(form.page_clamped(), 10),
        form=form,
    )


@app.route("/recipes/new", methods=["GET", "POST"])
@login_required
def create_recipe():
    form = EditRecipeForm()
    if request.method == "GET" or not form.validate():
        return render_edit_form(
            url_for("create_recipe"),
            url_for("get_recipes"),
            form,
        )
    recipe = Recipe(
        name=form.name.data,
        description=form.description.data,
        steps=form.steps.data,
    )
    recipe.account_id = current_user.id
    db.session().add(recipe)
    db.session().flush()
    recipe.insert_ingredients_from_form(form)
    db.session().commit()
    return redirect(url_for("get_recipes"))


@app.route("/recipes/<int:recipe_id>")
@login_required
def get_recipe(recipe_id: int):
    recipe = Recipe.query.filter_by(
        id=recipe_id,
        account_id=current_user.id,
    ).first_or_404()
    groups = []
    groups_by_id = {}
    ingredients_by_id = {}
    for ingredient in recipe.get_ingredients():
        group = groups_by_id.get(ingredient["group_name"])
        if group is None:
            group = []
            groups_by_id[ingredient["group_name"]] = group
            groups.append({
                "name": ingredient["group_name"],
                "ingredients": group,
            })
        values = {
            "id": ingredient["id"],
            "name": ingredient["name"],
            "amount": RecipeIngredientForm.join_amount(
                ingredient["amount"],
                ingredient["amount_unit"],
            ),
            "shopping_list_amounts": [],
        }
        existing_ingredient = ingredients_by_id.setdefault(
            ingredient["id"], values)
        values["shopping_list_amounts"] = existing_ingredient["shopping_list_amounts"]
        group.append(values)
    for x in recipe.get_shopping_list_amounts():
        ingredients_by_id[x["id"]]["shopping_list_amounts"].append(
            RecipeIngredientForm.join_amount(
                x["amount"],
                x["unit"],
            ),
        )
    return render_template(
        "recipes/recipe.html",
        recipe=recipe,
        groups=groups,
    )


@app.route("/recipes/<int:recipe_id>/edit")
@login_required
def edit_recipe(recipe_id: int):
    recipe = Recipe.query.filter_by(
        id=recipe_id,
        account_id=current_user.id,
    ).first_or_404()
    form = EditRecipeForm()
    form.name.data = recipe.name
    form.description.data = recipe.description
    form.steps.data = recipe.steps
    for recipe_ingredient in recipe.get_ingredients():
        form.ingredient_amounts.append_entry({
            "name": recipe_ingredient["name"],
            "amount": RecipeIngredientForm.join_amount(
                recipe_ingredient["amount"],
                recipe_ingredient["amount_unit"],
            ),
            "group": recipe_ingredient["group_name"],
        })
    return render_edit_form(
        url_for("update_recipe", recipe_id=recipe_id),
        url_for('get_recipe', recipe_id=recipe_id),
        form
    )


@app.route("/recipes/<int:recipe_id>", methods=["POST"])
@login_required
def update_recipe(recipe_id: int):
    form = EditRecipeForm(request.form)
    if not form.validate():
        return render_edit_form(
            url_for("update_recipe", recipe_id=recipe_id),
            url_for('get_recipe', recipe_id=recipe_id),
            form,
        )
    recipe = Recipe.query.filter_by(
        id=recipe_id,
        account_id=current_user.id,
    ).first_or_404()
    recipe.name = form.name.data
    recipe.description = form.description.data
    recipe.steps = form.steps.data
    RecipeIngredient.query.filter_by(recipe_id=recipe.id).delete()
    db.session.flush()
    recipe.insert_ingredients_from_form(form)
    Ingredient.delete_unused_ingredients(current_user.id)
    db.session().commit()
    return redirect(url_for("get_recipe", recipe_id=recipe_id))


@app.route("/recipes/<int:recipe_id>/delete", methods=["GET", "POST"])
@login_required
def delete_recipe(recipe_id: int):
    if request.method == "GET":
        return redirect(url_for("get_recipe", recipe_id=recipe_id))
    Recipe.query.filter_by(
        id=recipe_id,
        account_id=current_user.id,
    ).delete()
    db.session().flush()
    Ingredient.delete_unused_ingredients(current_user.id)
    db.session().commit()
    return redirect(url_for("get_recipes"))

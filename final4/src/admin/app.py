# src/admin/app.py
"""Flask Admin Panel для Final 4"""

import os
import sys
from datetime import datetime, timezone

from flask import Flask, redirect, url_for, request, render_template
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

# Добавляем корень проекта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.admin.models import db, User, Team, Match, Tournament, Transaction


# ==================== AUTH ====================

ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'final4admin'))


class AdminUser(UserMixin):
    id = 1
    username = 'admin'


admin_user = AdminUser()
login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    if str(user_id) == '1':
        return admin_user
    return None


# ==================== VIEWS ====================


class AuthMixin:
    def is_accessible(self):
        return current_user.is_authenticated
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))


class DashboardView(AuthMixin, AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        
        user_count = User.query.count()
        match_count = Match.query.count()
        active_matches = Match.query.filter(Match.status.in_([
            'waiting_for_opponent', 'setting_lineup', 'in_progress', 'extra_time', 'penalties'
        ])).count()
        tournament_count = Tournament.query.count()
        top_players = User.query.filter(User.telegram_id.isnot(None)).order_by(User.rating.desc()).limit(10).all()
        recent_matches = Match.query.order_by(Match.created_at.desc()).limit(10).all()
        
        return self.render(
            'admin/dashboard.html',
            user_count=user_count,
            match_count=match_count,
            active_matches=active_matches,
            tournament_count=tournament_count,
            top_players=top_players,
            recent_matches=recent_matches,
        )


class UserView(AuthMixin, ModelView):
    column_list = [
        'username', 'telegram_id', 'plan', 'rating',
        'matches_played', 'matches_won', 'is_banned', 'created_at', 'last_active_at'
    ]
    column_searchable_list = ['username', 'telegram_id']
    column_filters = ['is_banned', 'plan', 'rating', 'matches_played']
    column_sortable_list = ['username', 'rating', 'matches_played', 'matches_won', 'created_at']
    column_default_sort = ('rating', True)
    column_labels = {
        'username': 'Name',
        'telegram_id': 'Telegram ID',
        'matches_played': 'Played',
        'matches_won': 'Won',
        'is_banned': 'Banned',
        'created_at': 'Registered',
        'last_active_at': 'Last Active',
    }
    form_excluded_columns = ['teams', 'transactions', 'matches_as_m1', 'matches_as_m2']
    page_size = 50


class TeamView(AuthMixin, ModelView):
    column_list = ['name', 'user', 'formation', 'created_at']
    column_searchable_list = ['name']
    column_filters = ['formation']
    form_excluded_columns = ['players']  # JSONB too complex for form
    page_size = 50


class MatchView(AuthMixin, ModelView):
    column_list = [
        'id', 'match_type', 'status', 'phase',
        'score_manager1', 'score_manager2', 'decided_by',
        'penalty_score_m1', 'penalty_score_m2',
        'platform', 'created_at', 'finished_at'
    ]
    column_searchable_list = ['status', 'match_type']
    column_filters = ['status', 'match_type', 'phase', 'platform', 'decided_by']
    column_sortable_list = ['status', 'created_at', 'finished_at', 'score_manager1', 'score_manager2']
    column_default_sort = ('created_at', True)
    column_labels = {
        'score_manager1': 'Score M1',
        'score_manager2': 'Score M2',
        'penalty_score_m1': 'Pen M1',
        'penalty_score_m2': 'Pen M2',
        'match_type': 'Type',
    }
    # JSONB fields read-only in list, editable in detail
    form_excluded_columns = [
        'team1_snapshot', 'team2_snapshot', 'current_turn',
        'whistle_deck', 'whistle_cards_drawn', 'bets',
        'used_players_main_m1', 'used_players_main_m2',
        'used_players_extra_m1', 'used_players_extra_m2',
        'penalty_results', 'manager1', 'manager2'
    ]
    page_size = 50


class TournamentView(AuthMixin, ModelView):
    column_list = ['name', 'status', 'max_participants', 'entry_fee', 'prize_pool', 'format', 'starts_at']
    column_searchable_list = ['name']
    column_filters = ['status', 'format']
    column_sortable_list = ['name', 'status', 'starts_at', 'prize_pool']
    column_default_sort = ('created_at', True)
    form_excluded_columns = ['participants', 'bracket']
    page_size = 50


class TransactionView(AuthMixin, ModelView):
    column_list = ['user', 'type', 'amount', 'currency', 'description', 'created_at']
    column_searchable_list = ['type', 'description']
    column_filters = ['type', 'currency', 'amount']
    column_sortable_list = ['type', 'amount', 'created_at']
    column_default_sort = ('created_at', True)
    page_size = 50


# ==================== APP FACTORY ====================


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
    )
    
    db_url = os.environ.get(
        'DATABASE_URL',
        'postgresql://final4:final4_password@localhost:5432/final4'
    )
    
    app.config['SECRET_KEY'] = os.environ.get('ADMIN_SECRET_KEY', 'final4-admin-secret-key-change-me')
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    # Flask-Admin
    admin = Admin(
        app,
        name='Final 4 Admin',
        index_view=DashboardView(),
    )
    
    admin.add_view(UserView(User, db.session, name='Users', endpoint='users_admin'))
    admin.add_view(TeamView(Team, db.session, name='Teams', endpoint='teams_admin'))
    admin.add_view(MatchView(Match, db.session, name='Matches', endpoint='matches_admin'))
    admin.add_view(TournamentView(Tournament, db.session, name='Tournaments', endpoint='tournaments_admin'))
    admin.add_view(TransactionView(Transaction, db.session, name='Transactions', endpoint='transactions_admin'))
    
    # Login/Logout routes
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('admin.index'))
        
        error = None
        if request.method == 'POST':
            password = request.form.get('password', '')
            if check_password_hash(ADMIN_PASSWORD_HASH, password):
                login_user(admin_user)
                return redirect(url_for('admin.index'))
            else:
                error = 'Wrong password'
        
        return render_template('admin/login.html', error=error)
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))
    
    # Create tables for new models (tournaments, transactions)
    with app.app_context():
        db.create_all()
    
    return app

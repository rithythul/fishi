"""
MiroFish Backend - Flask应use工厂
"""

import os
import warnings

# suppress multiprocessing resource_tracker warnings（from third-party libraries如 transformers）
# 需wantin所have其heimport之前set
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask应use工厂function"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # setJSON编码：确保 文直接显示（andnotis \uXXXX format）
    # Flask >= 2.3 use app.json.ensure_ascii，旧版本use JSON_AS_ASCII configuration
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # setlog
    logger = setup_logger('mirofish')
    
    # only print startup information in reloader child process（avoid printing twice in debug mode）
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend starting...")
        logger.info("=" * 50)
    
    # 启useCORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # 注册simulation process cleanup function（确保service器关闭时终止所havesimulation process）
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("already registeredsimulation process cleanup function")
    
    # requestlog 间件
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"request: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"request body: {request.get_json(silent=True)}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"response: {response.status_code}")
        return response
    
    # Register blueprints
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    
    # 健康check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}
    
    if should_log_startup:
        logger.info("MiroFish Backend start completed")
    
    return app


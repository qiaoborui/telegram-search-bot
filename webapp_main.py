#!/usr/bin/env python
# -*- coding: utf-8 -*-

from webapp import app

if __name__ == '__main__':
    # 获取端口号，默认为8080
    import os
    port = int(os.environ.get('PORT', 8080))
    
    # 是否开启调试模式
    debug_mode = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
    
    # 启动Flask应用
    app.run(host='0.0.0.0', port=port, debug=debug_mode) 
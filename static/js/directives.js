angular.module('ecsmate.directives', []).
directive('navbar', function(){
	return {
		restrict: 'A',
		transclude: true,
		scope: {},
		controller: ['$scope', '$rootScope', function($scope, $rootScope){
			$rootScope.navbar_loaded = true;
		}],
		template: '<div class="navbar">\
				<div class="navbar-inner">\
					<div class="container">\
						<button type="button" class="btn btn-navbar" data-toggle="collapse" data-target=".nav-collapse">\
							<span class="icon-bar"></span>\
							<span class="icon-bar"></span>\
							<span class="icon-bar"></span>\
						</button>\
						<a class="brand" href="#/main">ECSMate</a>\
						<div class="nav-collapse collapse">\
							<ul class="nav">\
								<li ng-class="\'active\' | ifmatch:[currentItem,\'main\']"><a href="#/main">首页</a></li>\
								<li ng-class="\'active\' | ifmatch:[currentItem,\'account\']"><a href="#/account">帐号管理</a></li>\
								<li ng-class="\'active\' | ifmatch:[currentItem,\'ecs\']"><a href="#/ecs">云服务器管理</a></li>\
								<li><a href="/buyecs" target="_blank">购买云服务器</a></li>\
							</ul>\
							<ul class="nav pull-right">\
								<li ng-class="\'active\' | ifmatch:[currentItem,\'setting(\..*)?\']"><a href="#/setting">设置</a></li>\
								<li class="divider-vertical"></li>\
								<li ng-class="\'active\' | ifmatch:[currentItem,\'logout\']"><a href="#/logout">退出</a></li>\
							</ul>\
						</div>\
					</div>\
				</div>\
			</div>',
		replace: true
	};
}).
directive('loading', function(){
	return {
		restrict: 'A',
		transclude: true,
		scope: {},
		controller: ['$scope', function($scope){
			if (!$scope.loadingText) $scope.loadingText = '模块加载中，请稍候......';
		}],
		template: '<div style="padding:30px 0 10px 30px;">\
			<h6>{{loadingText}}</h6>\
			<div class="progress progress-striped active" style="width:230px">\
			<div class="bar" style="width:100%;"></div>\
			</div></div>',
		replace: true
	};
}).
directive('message', function(){
	return {
		restrict: 'A',
		transclude: true,
		scope: {},
		controller: ['$scope', '$rootScope', function($scope, $rootScope){
			$rootScope.showErrorMsg = false;
			$rootScope.errorMessage = '';
			$rootScope.showSuccessMsg = false;
			$rootScope.successMessage = '';
			$rootScope.showWarningMsg = false;
			$rootScope.warningMessage = '';
			$rootScope.showInfoMsg = false;
			$rootScope.infoMessage = '';
			$scope.$rootScope = $rootScope;
			if (!$scope.id) $scope.id = 'message';
		}],
		template: '<div id="{{id}}" style="position:fixed;left:0;bottom:0;width:100%;z-index:100">\
			<div class="container">\
				<div class="alert alert-error" style="display:none;margin-bottom:3px" ng-show="$rootScope.showErrorMsg">\
				<button ng-click="$rootScope.showErrorMsg=false" type="button" class="close">&times;</button>\
				<span ng-bind-html-unsafe="$rootScope.errorMessage"></span></div>\
				<div class="alert alert-success" style="display:none;margin-bottom:3px" ng-show="$rootScope.showSuccessMsg">\
				<button ng-click="$rootScope.showSuccessMsg=false" type="button" class="close">&times;</button>\
				<span ng-bind-html-unsafe="$rootScope.successMessage"></span></div>\
				<div class="alert alert-warning" style="display:none;margin-bottom:3px" ng-show="$rootScope.showWarningMsg">\
				<button ng-click="$rootScope.showWarningMsg=false" type="button" class="close">&times;</button>\
				<span ng-bind-html-unsafe="$rootScope.warningMessage"></span></div>\
				<div class="alert alert-info" style="display:none;margin-bottom:3px" ng-show="$rootScope.showInfoMsg">\
				<button ng-click="$rootScope.showInfoMsg=false" type="button" class="close">&times;</button>\
				<span ng-bind-html-unsafe="$rootScope.infoMessage"></span></div>\
			</div>\
			</div>',
		replace: true
	};
}).
directive('autofocus', function(){
	return function($scope, element){
		element[0].focus();
	};
});
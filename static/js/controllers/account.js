var AccountCtrl = [
'$scope', '$rootScope', '$location', 'Module', 'Request',
function($scope, $rootScope, $location, Module, Request){
	var module = 'account';
	Module.init(module, '帐号管理');
	$scope.accounts = [];
	$scope.loaded = false;
	
	$scope.load = function(quiet){
		Request.get('/account', function(data){
			if (data.code == 0) {
				$scope.accounts = data.data;
			}
			$scope.loaded = true;
		}, false, quiet);
	};

	$scope.addconfirm = function(account){
		$scope.newaccount = {
			'name': '',
			'access_key_id': '',
			'access_key_secret': '',
			'status': true
		};
		$('#addconfirm').modal();
	};
	$scope.add = function(){
		Request.post('/account', {
			'action': 'add',
			'name': $scope.newaccount.name,
			'access_key_id': $scope.newaccount.access_key_id,
			'access_key_secret': $scope.newaccount.access_key_secret,
			'status': $scope.newaccount.status
		}, function(){
			$scope.load(true);
		});
	};
	
	$scope.editconfirm = function(account){
		$scope.curaccount = account;
		$scope.curaccount.old_access_key_id = account.access_key_id;
		$('#editconfirm').modal();
	};
	$scope.update = function(){
		Request.post('/account', {
			'action': 'update',
			'old_access_key_id': $scope.curaccount.old_access_key_id,
			'name': $scope.curaccount.name,
			'access_key_id': $scope.curaccount.access_key_id,
			'access_key_secret': $scope.curaccount.access_key_secret,
			'status': $scope.curaccount.status
		}, function(){
			$scope.load(true);
		});
	};

	$scope.removeconfirm = function(account){
		$scope.curaccount = account;
		$('#removeconfirm').modal();
	};
	$scope.remove = function(){
		Request.post('/account', {
			'action': 'delete',
			'access_key_id': $scope.curaccount.access_key_id
		}, function(){
			$scope.load(true);
		});
	};
}];
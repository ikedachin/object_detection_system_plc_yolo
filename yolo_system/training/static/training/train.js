document.addEventListener('DOMContentLoaded', function() {
    const projectSelect = document.getElementById('project_name');
    const datasetYamlSelect = document.getElementById('dataset_yaml');
    const datasetYamlFullpath = document.getElementById('dataset_yaml_fullpath');
    const dataTypeSelect = document.getElementById('data_type');

    // 初期表示時にhidden値を正しくセット
    if (datasetYamlSelect && datasetYamlFullpath) {
        if (datasetYamlSelect.options.length > 0) {
            datasetYamlFullpath.value = datasetYamlSelect.options[datasetYamlSelect.selectedIndex].getAttribute('data-fullpath');
        } else {
            datasetYamlFullpath.value = '';
        }
    }

    // yamlセレクトボックスの選択変更時にhidden値も更新
    if (datasetYamlSelect && datasetYamlFullpath) {
        datasetYamlSelect.addEventListener('change', function() {
            if (datasetYamlSelect.selectedIndex >= 0) {
                const opt = datasetYamlSelect.options[datasetYamlSelect.selectedIndex];
                datasetYamlFullpath.value = opt.getAttribute('data-fullpath') || '';
            } else {
                datasetYamlFullpath.value = '';
            }
        });
    }

    // is_activeなプロジェクトを自動選択（サーバー側でselected付与しているが、JSでも補助）
    if (projectSelect) {
        let foundActive = false;
        for (let i = 0; i < projectSelect.options.length; i++) {
            const opt = projectSelect.options[i];
            if (opt.getAttribute('data-is-active') === 'true') {
                projectSelect.selectedIndex = i;
                foundActive = true;
                break;
            }
        }
        if (!foundActive && projectSelect.options.length > 0) {
            projectSelect.selectedIndex = 0;
        }

        // プロジェクト選択時にAjaxでyamlリストを取得し、セレクトを書き換える
        projectSelect.addEventListener('change', function() {
            const selectedProject = projectSelect.value;
            const dataType = dataTypeSelect ? dataTypeSelect.value : '';
            fetch(`?project_name=${encodeURIComponent(selectedProject)}&data_type=${encodeURIComponent(dataType)}`)
                .then(res => res.json())
                .then(data => {
                    if (datasetYamlSelect) {
                        datasetYamlSelect.innerHTML = '';
                        if (data.yamls && data.yamls.length > 0) {
                            data.yamls.forEach(function(yaml, idx) {
                                const opt = document.createElement('option');
                                opt.value = yaml.name;
                                opt.textContent = yaml.name;
                                opt.setAttribute('data-fullpath', yaml.fullpath);
                                datasetYamlSelect.appendChild(opt);
                            });
                            datasetYamlSelect.disabled = false;
                            // hiddenにもセット
                            if (datasetYamlFullpath) {
                                datasetYamlFullpath.value = data.yamls[0].fullpath;
                            }
                        } else {
                            datasetYamlSelect.disabled = true;
                            if (datasetYamlFullpath) {
                                datasetYamlFullpath.value = '';
                            }
                        }
                    }
                });
        });
    }

    // データ種別変更時も同様にyamlリストを更新
    if (dataTypeSelect) {
        dataTypeSelect.addEventListener('change', function() {
            const selectedProject = projectSelect ? projectSelect.value : '';
            const dataType = dataTypeSelect.value;
            fetch(`?project_name=${encodeURIComponent(selectedProject)}&data_type=${encodeURIComponent(dataType)}`)
                .then(res => res.json())
                .then(data => {
                    if (datasetYamlSelect) {
                        datasetYamlSelect.innerHTML = '';
                        if (data.yamls && data.yamls.length > 0) {
                            data.yamls.forEach(function(yaml, idx) {
                                const opt = document.createElement('option');
                                opt.value = yaml.name;
                                opt.textContent = yaml.name;
                                opt.setAttribute('data-fullpath', yaml.fullpath);
                                datasetYamlSelect.appendChild(opt);
                            });
                            datasetYamlSelect.disabled = false;
                            if (datasetYamlFullpath) {
                                datasetYamlFullpath.value = data.yamls[0].fullpath;
                            }
                        } else {
                            datasetYamlSelect.disabled = true;
                            if (datasetYamlFullpath) {
                                datasetYamlFullpath.value = '';
                            }
                        }
                    }
                });
        });
    }

    const form = document.getElementById('trainForm');
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(form);
        fetch('', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => response.json())
        .then(data => {
            const resultDiv = document.getElementById('trainResult');
            if (data.success) {
                resultDiv.innerHTML = `<div class='alert alert-success'>学習が完了しました。<br>モデル: ${data.model_path}<br>メトリクス: ${JSON.stringify(data.metrics)}</div>`;
            } else {
                resultDiv.innerHTML = `<div class='alert alert-danger'>エラー: ${data.error}</div>`;
            }
        })
        .catch(err => {
            document.getElementById('trainResult').innerHTML = `<div class='alert alert-danger'>通信エラー: ${err}</div>`;
        });
    });
});
